import time
from abc import ABC, abstractmethod
try:
    from Resource import Status
    from Utils import WAIT_TIME
except Exception as e:
    from .Resource import Status
    from .Utils import WAIT_TIME
import logging

class Procedure(ABC):
    """Abstract base class for all lab procedures."""

    @abstractmethod
    def run(self):
        """Execute the procedure."""
        pass


class ResourceProcedure(Procedure):
    """
    Generic procedure for operating a lab instrument:
    Wait until available → Connect → Action → Disconnect
    """

    def __init__(self, resource, result_keyword=None, wait_time=10, poll_interval=0.1, *action_args, **action_kwargs):
        """
        Initialize a procedure for a specific resource.

        Parameters:
            resource: Object that implements connect(), action(), and disconnect() methods, and has a .status attribute.
            result_keyword: Optional key to label the result when returning.
            wait_time: Maximum time (seconds) to wait for the resource to become available.
            poll_interval: Time interval (seconds) between each status check while waiting.
            *action_args, **action_kwargs: Arguments to pass to resource.action() when executed.
        """
        super().__init__()
        self.resource = resource
        self.wait_time = wait_time
        self.poll_interval = poll_interval
        self.action_args = action_args
        self.action_kwargs = action_kwargs
        self.result_keyword = result_keyword

    def run(self):
        result = 0
        time.sleep(5)
        """
        Execute the procedure lifecycle:
            1. Wait until the resource is available.
            2. Connect to the resource.
            3. Perform the action on the resource.
            4. Disconnect from the resource.

        Returns:
            The result of resource.action(), optionally wrapped in a dict with result_keyword as the key.
        """
        '''
        start_time = time.time()

        # Wait for the resource to become available
        while self.resource.status.value != Status.AVAILABLE.value:
            elapsed = time.time() - start_time
            if elapsed >= self.wait_time:
                # Timeout error if resource never became available
                raise RuntimeError(
                    f"Instrument {self.instrument.name} did not become available after {self.wait_time} seconds"
                )
            time.sleep(self.poll_interval)

        try:
            # Step 1: Connect to the resource
            self.resource.connect()

            # Step 2: Execute the resource action
            result = self.resource.action(*self.action_args, **self.action_kwargs)

        finally:
            # Step 3: Always disconnect even if an error occurs
            try:
                self.resource.disconnect()
            except Exception as e:
                # Log disconnect errors but do not re-raise to preserve primary error
                self.resource.log(f"Error during disconnect: {e}", level=logging.ERROR)
'''
        # Optionally wrap result in a dictionary
        if self.result_keyword:
            return {self.result_keyword: result}


class WaitProcedure(Procedure):
    """A simple procedure that waits for a specified duration."""

    def __init__(self, duration):
        """
        Parameters:
            duration: Time to wait in seconds.
        """
        self.duration = duration

    def run(self):
        """Pause execution for the specified duration."""
        time.sleep(self.duration)


class GenerateProcedure(Procedure):
    """
    A procedure that generates a sequence of action dictionaries.
    Each dictionary specifies an operation to perform.
    """

    def __init__(self, arg_list):
        """
        Parameters:
            arg_list: A list of dicts, each containing:
                      - 'id': target resource ID
                      - 'args': positional arguments for the action
                      - 'kwargs': keyword arguments for the action
        """
        self.arg_list = arg_list

    def run(self):
        """
        Convert the arg_list into a standardized list of command dicts.

        Returns:
            List of command dictionaries with keys: 'id', 'args', 'kwargs'
        """
        result = []
        for current in self.arg_list:
            result.append({"id": current["id"], "args": current["args"], "kwargs": current["kwargs"]})
        return result
