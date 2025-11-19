import imapclient
import threading
import time
import logging
from datetime import datetime
from typing import Callable, Dict, List, Tuple
import config

logger = logging.getLogger(__name__)


class IMAPIdleMonitor:
    """
    Monitor multiple IMAP folders using IDLE for real-time change detection.

    Each folder is monitored in a separate thread. When changes are detected
    (new messages, expunges, flag changes), a callback is triggered.
    """

    def __init__(self,
                 user_email: str,
                 password: str,
                 folders: List[str],
                 on_change_callback: Callable[[str, str], None],
                 idle_timeout: int = None):
        """
        Initialize IMAP IDLE monitor.

        Args:
            user_email: IMAP account email
            password: IMAP account password
            folders: List of folder names to monitor
            on_change_callback: Function to call when changes detected (folder, user_email)
            idle_timeout: IDLE timeout in seconds (default from config, max 29 min per RFC 2177)
        """
        self.user_email = user_email
        self.password = password
        self.folders = folders
        self.on_change_callback = on_change_callback
        self.idle_timeout = idle_timeout if idle_timeout is not None else config.IDLE_TIMEOUT

        # Thread management
        self.threads: Dict[str, threading.Thread] = {}
        self.stop_events: Dict[str, threading.Event] = {}
        self.running = False

        # Connection tracking
        self.clients: Dict[str, imapclient.IMAPClient] = {}
        self.last_change_time: Dict[str, datetime] = {}

    def start(self):
        """Start monitoring all folders"""
        if self.running:
            logger.warning(f"IDLE monitor already running for {self.user_email}")
            return

        self.running = True
        logger.info(f"Starting IMAP IDLE monitor for {self.user_email}")
        logger.info(f"  Monitoring folders: {', '.join(self.folders)}")

        # Start a thread for each folder
        for folder in self.folders:
            self.stop_events[folder] = threading.Event()
            thread = threading.Thread(
                target=self._monitor_folder,
                args=(folder,),
                name=f"IDLE-{self.user_email}-{folder}",
                daemon=True
            )
            self.threads[folder] = thread
            thread.start()
            logger.info(f"  Started IDLE thread for folder: {folder}")

    def stop(self):
        """Stop monitoring all folders"""
        if not self.running:
            return

        logger.info(f"Stopping IMAP IDLE monitor for {self.user_email}")
        self.running = False

        # Signal all threads to stop
        for folder, stop_event in self.stop_events.items():
            stop_event.set()

        # Wait for all threads to finish
        for folder, thread in self.threads.items():
            if thread.is_alive():
                logger.info(f"  Waiting for {folder} thread to finish...")
                thread.join(timeout=5)
                if thread.is_alive():
                    logger.warning(f"  Thread for {folder} did not stop cleanly")

        # Close all IMAP connections
        for folder, client in self.clients.items():
            try:
                if client:
                    client.logout()
                    logger.info(f"  Closed IMAP connection for {folder}")
            except Exception as e:
                logger.error(f"  Error closing connection for {folder}: {e}")

        self.clients.clear()
        self.threads.clear()
        self.stop_events.clear()
        logger.info(f"IMAP IDLE monitor stopped for {self.user_email}")

    def _connect(self, folder: str) -> imapclient.IMAPClient:
        """
        Create and configure IMAP connection for a folder.

        Args:
            folder: Folder name to select

        Returns:
            Configured IMAPClient instance
        """
        try:
            client = imapclient.IMAPClient(
                config.IMAP_HOST,
                port=config.IMAP_PORT,
                ssl=True
            )
            client.login(self.user_email, self.password)

            # Select the folder (readonly to avoid conflicts)
            client.select_folder(folder, readonly=True)

            logger.info(f"Connected to IMAP for {self.user_email}/{folder}")
            return client

        except Exception as e:
            logger.error(f"Failed to connect to IMAP for {self.user_email}/{folder}: {e}")
            raise

    def _monitor_folder(self, folder: str):
        """
        Monitor a single folder using IMAP IDLE.

        This runs in a dedicated thread per folder. It handles:
        - IDLE timeout renewal
        - Connection errors and reconnection
        - Change detection and callback triggering

        Args:
            folder: Folder name to monitor
        """
        stop_event = self.stop_events[folder]
        client = None
        reconnect_delay = 1  # Start with 1 second, exponential backoff
        max_reconnect_delay = 300  # Max 5 minutes between reconnects

        logger.info(f"[{folder}] IDLE monitor thread started for {self.user_email}")

        while not stop_event.is_set():
            try:
                # Connect if not connected
                if client is None:
                    client = self._connect(folder)
                    self.clients[folder] = client
                    reconnect_delay = 1  # Reset reconnect delay on successful connection

                # Enter IDLE mode
                logger.debug(f"[{folder}] Entering IDLE mode (timeout: {self.idle_timeout}s)")
                client.idle()

                # Wait for changes or timeout
                # Check every 60 seconds if we should stop, but stay in IDLE
                idle_start = time.time()
                while not stop_event.is_set():
                    # Check for IDLE responses with a short timeout
                    remaining_time = self.idle_timeout - (time.time() - idle_start)

                    if remaining_time <= 0:
                        # IDLE timeout approaching, need to renew
                        logger.debug(f"[{folder}] IDLE timeout reached, renewing...")
                        break

                    # Check for changes with a short timeout (10 seconds)
                    check_timeout = min(10, remaining_time)
                    responses = client.idle_check(timeout=check_timeout)

                    if responses:
                        # Changes detected!
                        logger.info(f"[{folder}] IDLE detected changes: {responses}")
                        self.last_change_time[folder] = datetime.now()

                        # Exit IDLE before triggering callback
                        client.idle_done()

                        # Trigger the callback
                        try:
                            logger.info(f"[{folder}] Triggering reclassification check for {self.user_email}")
                            self.on_change_callback(folder, self.user_email)
                        except Exception as e:
                            logger.error(f"[{folder}] Error in change callback: {e}")

                        # Break to restart IDLE
                        break
                else:
                    # Stop event was set during IDLE
                    if client:
                        try:
                            client.idle_done()
                        except:
                            pass
                    break

                # Exit IDLE mode cleanly
                try:
                    client.idle_done()
                except Exception as e:
                    # May have already exited IDLE
                    logger.debug(f"[{folder}] Error exiting IDLE (may already be done): {e}")

            except Exception as e:
                logger.error(f"[{folder}] Error in IDLE monitor for {self.user_email}: {e}")

                # Close broken connection
                if client:
                    try:
                        client.logout()
                    except:
                        pass
                    client = None
                    self.clients[folder] = None

                # Wait before reconnecting (exponential backoff)
                if not stop_event.is_set():
                    logger.info(f"[{folder}] Reconnecting in {reconnect_delay} seconds...")
                    stop_event.wait(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)

        # Cleanup when thread stops
        if client:
            try:
                client.logout()
                logger.info(f"[{folder}] Logged out from IMAP")
            except:
                pass

        logger.info(f"[{folder}] IDLE monitor thread stopped for {self.user_email}")

    def get_status(self) -> Dict[str, Dict]:
        """
        Get status of all monitored folders.

        Returns:
            Dict mapping folder name to status info
        """
        status = {}
        for folder in self.folders:
            thread = self.threads.get(folder)
            status[folder] = {
                'running': thread.is_alive() if thread else False,
                'connected': self.clients.get(folder) is not None,
                'last_change': self.last_change_time.get(folder),
            }
        return status


class IMAPIdleMonitorManager:
    """
    Manages IMAP IDLE monitors for multiple users.
    """

    def __init__(self, on_change_callback: Callable[[str, str], None]):
        """
        Initialize monitor manager.

        Args:
            on_change_callback: Function to call when changes detected (folder, user_email)
        """
        self.on_change_callback = on_change_callback
        self.monitors: Dict[str, IMAPIdleMonitor] = {}
        self.running = False

    def start(self):
        """Start IDLE monitors for all configured users"""
        if self.running:
            logger.warning("IDLE monitor manager already running")
            return

        self.running = True
        logger.info("Starting IMAP IDLE monitor manager")

        # Get folders to monitor from FOLDER_MAP
        folders = list(config.FOLDER_MAP.values())

        # Create a monitor for each user
        for user_email, password in config.IMAP_USERS:
            try:
                monitor = IMAPIdleMonitor(
                    user_email=user_email,
                    password=password,
                    folders=folders,
                    on_change_callback=self.on_change_callback
                )
                monitor.start()
                self.monitors[user_email] = monitor
                logger.info(f"Started IDLE monitor for {user_email}")
            except Exception as e:
                logger.error(f"Failed to start IDLE monitor for {user_email}: {e}")

        logger.info(f"IDLE monitor manager started ({len(self.monitors)} users)")

    def stop(self):
        """Stop all IDLE monitors"""
        if not self.running:
            return

        logger.info("Stopping IMAP IDLE monitor manager")
        self.running = False

        for user_email, monitor in self.monitors.items():
            try:
                monitor.stop()
                logger.info(f"Stopped IDLE monitor for {user_email}")
            except Exception as e:
                logger.error(f"Error stopping IDLE monitor for {user_email}: {e}")

        self.monitors.clear()
        logger.info("IMAP IDLE monitor manager stopped")

    def get_status(self) -> Dict[str, Dict]:
        """
        Get status of all monitors.

        Returns:
            Dict mapping user email to monitor status
        """
        return {
            user_email: monitor.get_status()
            for user_email, monitor in self.monitors.items()
        }
