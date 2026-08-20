# -*- coding: utf-8 -*-
"""
optional_abstractmethod.py: Decorator for optional abstract methods.

EXAMPLE
@optional_abstractmethod
def some_function_that can be derived():
    ...

edward | 2025-11-03

"""

from functools import wraps



def optional_abstractmethod(func):
    """
    Decorator for optional abstract methods.
    Child classes are not required to implement this method,
    but if they call it without implementing it, a NotImplementedError is raised.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # Check if the method has been overridden in a subclass
        method_owner = None
        for cls in type(self).__mro__:
            if func.__name__ in cls.__dict__:
                method_owner = cls.__dict__[func.__name__]
                break
        
        # If it's still the decorated base method, raise error
        if method_owner is wrapper or method_owner is func:
            raise NotImplementedError(
                f"Method '{func.__name__}' is not implemented in {self.__class__.__name__}"
            )
        
        # Otherwise call the overridden method
        return method_owner(self, *args, **kwargs)
    
    return wrapper

