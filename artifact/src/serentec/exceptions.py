# -*- coding: utf-8 -*-
"""
Here we define root exceptions for Serentec.

As per Slatkin's Chapter 7.
"""

from typing import Optional

# serentec: logging
from serentec.utils.logger import logger_dl
module_logger = logger_dl.getChild("Serentec: Exception")


class SerentecException(Exception):

    """
    Base-class for all exceptions raised within the Serentec namespace
    """
    
    def __init__(self, msg):
        # catch the Exception initalisation and log the error to stdout
        # BACKLOG: store to ModelDB
        #module_logger.error(msg)
        pass

    
class Error(SerentecException):
    """A general type of error"""
    pass

class CannotAcquireLock(SerentecException):
    """Could not acquire the lock on an object"""
    pass

# --- for models that predict JSON; e.g file type inference
class JSONPredictionNotValid(SerentecException):
    """A prediction from a model predicting JSON was not in a valid JSON format"""    
    pass

class JSONPredictionMissingField(SerentecException):
    """A prediction from a model predicting JSON did not contain a required field"""    
    pass

# ---

class ArgumentTypeError(SerentecException):
    """Argument of the wrong type was passed to a function"""
    pass

class ArgumentMissing(SerentecException):
    """A required argument was missing"""
    pass


class ValueError(SerentecException):
    """Generic error, error related to the value of an item"""
    pass

class NotImplementedError(SerentecException):
    """Feature not yet implemented"""
    pass

class DeprecatedError(SerentecException):
    """Feature has been deprecated"""
    pass

class EmptyDataFrame(SerentecException):
    """An empty dataframe was passed as an argument"""
    pass


class EmptyKPIDataFrame(SerentecException):
    """An KPIDataFrame was passed as an argument"""
    pass

class MultipleTsInKPIDataFrame(SerentecException):
    """A KPIDataFrame was expected with only a single ts, but multiple ts_ids were found"""
    pass

class MultipleTsGroupsInKPIDataFrame(SerentecException):
    """A KPIDataFrame was expected with only a single ts group, but multiple ts_group_ids were found"""
    pass

class DataFrameNotFound(SerentecException):
    """A DataFrame was requested from a stream but was not found"""
    
    pass

class UnhandledDataFrequency(SerentecException):
    """Requested data frequency is not supported"""
    
    pass

# Dates
class UnableToInferDate(SerentecException):
    """It was not possible to infer information about the date from the data."""    
    pass

class UnableToParseDate(SerentecException):
    """It was not possible to parse the date string with the specified format."""    
    pass


class UnhandledFormat(SerentecException):
    """The specified format was unknown"""    
    pass

    
class UnhandledDateFormat(UnhandledFormat):
    """The specified date format was unknown"""    
    pass



class InsufficientSignalFromDateInference(SerentecException):
    """The inference on the date column did not generate enough signal"""    
    pass

class InferenceRequiresLocale(SerentecException):
    """interpretation of numerical weekday number is locale specific
    this is because weekday numbers are ambivalent in numerical form
    2 is Tuesday in fr_CH but is Monday in en_US (first week of the day is Sunday)
    
    """    
    pass


# Cache errors
class CacheGetException(SerentecException):
    """An object could not be retrieved from the Cache"""
    pass
    
class CacheSetException(SerentecException):
    """An object could not be set to the Cache"""
    pass

# Def
class DefNotFound(SerentecException):
    """A Def was requested from a stream but was not found"""    
    pass


class UnhandledDefVersion(SerentecException):
    """Version not handled; expected versions are v1, v2, etc"""    
    pass


class DefDataTypeUnhandled(SerentecException):
    """An unhandled datatype was used. Currently we only handle INT, STR, FLOAT, DATE, etc, as specified in Config"""    
    pass


class DefNotSerialisable(SerentecException):
    """Serialisation of a Def to JSON was requested but not possible"""    
    pass

class DefInferenceError(SerentecException):
    """A general error occurred during inference of the .def"""
    pass

class DefInvalid(SerentecException):
    """.def is invalid"""
    pass

class UnableToFindMeasure(SerentecException):
    """It was not possible to find at least one measure in the data."""    
    pass

class UnableToFindDimension(SerentecException):
    """It was not possible to find at least one dimension in the data.
    BACKLOG: Currently we require at least one dimension, although this is not strictly necessary.
    """    
    pass


class StreamInconsistency(SerentecException):
    """Inconsistent keys in the stream"""
    
    pass


class ParameterTypeError(SerentecException):
    """A paramter to a function was of the incorrect type"""
    pass

class ParamaterValueError(SerentecException):
    """A paramter to a function was of the correct type but incorrect value"""
    pass

class ColumnTypeNotInferredError(SerentecException):
    """Type of column could not be inferred"""
    pass


class ColumnNotFound(SerentecException):
    """The specified column does not exist in the def file"""
    pass


class MissingField(SerentecException):
    """A field in the data is missing"""
    pass


class EmptyField(SerentecException):
    """A field in the data exists but is empty"""
    pass


class RESTRequestError(SerentecException):
    """The requested remote RESTful data was not available"""
    pass


class DataNotDownloaded(SerentecException):
    """The requested data was not downloaded or no data was available"""
    pass

class DefMissingUUID(SerentecException):
    """One of the required UUIDs was not specified in the def
        - def_uuid
        - user_uuid
        - dataset_uuid
    
    """
    pass

# -- File System --
class PathNotFound(SerentecException):
    """The specified path does not exist on the filesystem"""
    pass

class FileNotFound(SerentecException):
    """The specified filename does not exist on the filesystem"""
    pass

class UnhandledFileType(SerentecException):
    """The file extension was not recognisned; typically we recognise .csv, .xls, etc"""
    filetype : Optional[str] = None
    
class IngestionError(SerentecException):
    """The DataFrame could not be read; this could happen when the incorrect filetype was predicted, e.g. predicted a parquet file and trying to read with from_parquet when the file is a csv"""
    filetype : Optional[str] = None
    msg : Optional[str] = None


class UnhandledCompressionType(SerentecException):
    """The specified compression type was not supported"""
    pass

# -- Data APIs --
class APINotFound(SerentecException):
    """The specified API could not be loaded"""
    pass

class APIFileNotFound(SerentecException):
    """A file within an API could not be loaded"""
    pass

# Backlog/Not Implemented
class NotImplementedError(SerentecException):
    """Technical debt..."""
    pass


# Database: general
class NotConnected(SerentecException):
    """Not connected to the database, typically when you try to execute a command and not connection was made
    or connection has been closed.
    
    """
    pass

class DatabaseConnectionError(SerentecException):
    """Could not connect to the database"""
    pass


class DatabaseExecutionError(SerentecException):
    """An error occurred whilst executing a statement"""
    pass

class MappingNotFound(SerentecException):
    """User looked up the name of an identifier that could not be found"""
    pass

class MappingNotBijective(SerentecException):
    """a mapping is not bijetive, for example value A may exist on two rows and point to values 1 and 2"""
    pass

# Database: data db

class DatasetNotFound(SerentecException):
    """the specified dataset in the data db was not found"""
    pass

class DatasetHasNoSnapshots(SerentecException):
    """the specified dataset in the data db has zero snapshots"""
    pass

class InvalidSnapshotId(SerentecException):
    """the specified snapshot id for the specified dataset in the data db is invalid"""
    pass

class SnapshotIdUndone(SerentecException):
    """the specified snapshot id for the specified dataset has been undone an is thus no longer valid"""
    pass

class ReservedColumnName(SerentecException):
    """column name is reserved by the COD"""
    pass

class PrimaryKeyNotFound(SerentecException):
    """the primary key(s) specified in the def were not found in the dataframe"""
    pass

class PrimaryKeyDuplicate(SerentecException):
    """two or more rows in the data have the same primary key"""
    pass

if __name__ == "__main__":
    raise Error("this is a SerenTec exception raised")
