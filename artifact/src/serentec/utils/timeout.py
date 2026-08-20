# -*- coding: utf-8 -*-
"""
timeout.py: decorator function for implementing a timeout on any Python function, including non-async functions

EXAMPLE
@timeout(5)  # Set timeout to 5 seconds
def potentially_hanging_function():
    ...

edward | 2025-05-09

USAGE
python3 timeout.py
"""

from functools import wraps
from signal import SIGALRM, signal, alarm


def timeout(function_timeout_seconds : int):
    """
    :param function_timeout_seconds: raise a timeout after this many seconds if functions is still running
    
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            def handle_timeout(signum, frame):
                raise TimeoutError(f"Function {func.__name__} timed out after {function_timeout_seconds} seconds")
            
            # Set the timeout handler
            original_handler = signal(SIGALRM, handle_timeout)
            # Set the alarm
            alarm(function_timeout_seconds)
            
            try:
                result = func(*args, **kwargs)
            finally:
                # Cancel the alarm and restore original handler
                alarm(0)
                signal(SIGALRM, original_handler)
            
            return result
        return wrapper
    return decorator


if __name__ == "__main__":

    import time

    def main():

        # Example usage
        @timeout(5)  # Set timeout to 5 seconds
        def potentially_hanging_function():
            # Your function code here
            i = 0
            while True:  
                # This will hang indefinitely; non async
                time.sleep(1)
                #print("Still running...")
                i += 1

                # test what happens if function has ended before the timeout
                #if i == 3:
                #    break

        # Now when you call this function, it will raise a TimeoutError after 5 seconds
        try:
            potentially_hanging_function()
        except TimeoutError as e:
            print(f"Caught exception: {e}")


    # main entry point
    main()

    


