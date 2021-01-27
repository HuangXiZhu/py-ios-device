"""
Some classes that can be encoded in a binary plist but don't map into
python's type hierarchy.
"""
import copy
import dataclasses
import uuid
from datetime import datetime, timezone
from typing import Optional
import dataclasses


class Error(Exception):
    pass


_IGNORE_UNMAPPED_KEY = "__bpylist_ignore_unmapped__"


def _verify_dataclass_has_fields(dataclass, plist_obj):
    if getattr(dataclass, _IGNORE_UNMAPPED_KEY, False):
        return

    dataclass_fields = dataclasses.fields(dataclass)

    skip_fields = {'$class'}

    fields_to_verify = plist_obj.keys() - skip_fields
    fields_with_no_dots = {
        (f if not f.startswith('NS.') else 'NS' + f[3:])
        for f in fields_to_verify}
    unmapped_fields = fields_with_no_dots - {f.name for f in dataclass_fields}
    if unmapped_fields:
        raise Error(
            f"Unmapped fields: {unmapped_fields} for class {dataclass}")


class DataclassArchiver:
    """Helper to easily map python dataclasses (PEP557) to archived objects.
    To create an archiver/unarchiver just subclass the dataclass from this
    helper, for example:
    @dataclasses.dataclass
    class MyObjType(DataclassArchiver):
        int_field: int = 0
        str_field: str = ""
        float_field: float = -1.1
        list_field: list = dataclasses.field(default_factory=list)
    and then register as usually:
    archiver.update_class_map(
            {'MyObjType': MyObjType }
    )
    If you are only interested in certain fields, you can ignore unmapped
    fields, so that no exception is raised:
    @dataclasses.dataclass
    class MyObjType(DataclassArchiver, ignore_unmapped=True):
        int_field: int = 0
        str_field: str = ""
    """

    def __init_subclass__(cls, ignore_unmapped=False):
        setattr(cls, _IGNORE_UNMAPPED_KEY, ignore_unmapped)

    @staticmethod
    def encode_archive(obj, archive):
        for field in dataclasses.fields(type(obj)):
            archive_field_name = field.name
            if archive_field_name[:2] == 'NS':
                archive_field_name = 'NS.' + archive_field_name[2:]
            archive.encode(archive_field_name, getattr(obj, field.name))

    @classmethod
    def decode_archive(cls, archive):
        _verify_dataclass_has_fields(cls, archive.object)
        field_values = {}
        for field in dataclasses.fields(cls):
            archive_field_name = field.name
            if archive_field_name[:2] == 'NS':
                archive_field_name = 'NS.' + archive_field_name[2:]
            value = archive.decode(archive_field_name)
            if isinstance(value, bytearray):
                value = bytes(value)
            field_values[field.name] = value
        return cls(**field_values)


class timestamp(float):
    """
    Represents the concept of time (in seconds) since the UNIX epoch.

    The topic of date and time representations in computers inherits many
    of the complexities of the topics of date and time representation before
    computers existed, and then brings its own revelations to the mess.

    Python seems to take a very Gregorian view of dates, but has enabled full
    madness for times.

    However, we want to store something more agnostic, something that can easily
    be used in computations and formatted for any particular collection of
    date and time conventions.

    Fortunately, the database we use, our API, and our Cocoa clients have made
    similar decisions. So to make the transmission of data to and from clients,
    we will use this class to store our agnostic representation.
    """

    unix2apple_epoch_delta = 978307200.0

    def encode_archive(obj, archive):
        "Delegate for packing timestamps back into the NSDate archive format"
        offset = obj - timestamp.unix2apple_epoch_delta
        archive.encode('NS.time', offset)

    def decode_archive(archive):
        "Delegate for unpacking NSDate objects from an archiver.Archive"
        offset = archive.decode('NS.time')
        return timestamp(timestamp.unix2apple_epoch_delta + offset)

    def __str__(self):
        return f"bpylist.timestamp {self.to_datetime().__repr__()}"

    def to_datetime(self) -> datetime:
        return datetime.fromtimestamp(self, timezone.utc)


class NSURL:
    "Delegate for packing/unpacking Url"

    def __init__(self, base, relative):
        self._base = base
        self._relative = relative

    def __eq__(self, other) -> bool:
        return self._base == other._base and self._relative == other._relative

    def __str__(self):
        return "NSURL({}, {})".format(self._base, self._relative)

    def __repr__(self):
        return self.__str__()

    def encode_archive(obj, archive):
        "Delegate for packing timestamps back into the NSDate archive format"
        archive.encode('NS.base', obj._base)
        archive.encode('NS.relative', obj._relative)

    def decode_archive(obj, archive):
        base = archive.decode('NS.base')
        relative = archive.decode('NS.relative')
        return {"$class": "NSURL", "base": base, "relative": relative}


class XCTestConfiguration:
    _default = {
        'aggregateStatisticsBeforeCrash': {
            'XCSuiteRecordsKey': {}
        },
        'automationFrameworkPath': '/Developer/Library/PrivateFrameworks/XCTAutomationSupport.framework',
        'baselineFileRelativePath': None,
        'baselineFileURL': None,
        'defaultTestExecutionTimeAllowance': None,
        'disablePerformanceMetrics': False,
        'emitOSLogs': False,
        'formatVersion': 2,  # store in UID
        'gatherLocalizableStringsData': False,
        'initializeForUITesting': True,
        'maximumTestExecutionTimeAllowance': None,
        'productModuleName': "WebDriverAgentRunner",  # set to other value is also OK
        'randomExecutionOrderingSeed': None,
        'reportActivities': True,
        'reportResultsToIDE': True,
        'systemAttachmentLifetime': 2,
        'targetApplicationArguments': [],  # maybe useless
        'targetApplicationBundleID': None,
        'targetApplicationEnvironment': None,
        'targetApplicationPath': None,
        'testApplicationDependencies': {},
        'testApplicationUserOverrides': None,
        'testBundleRelativePath': None,
        'testExecutionOrdering': 0,
        'testTimeoutsEnabled': False,
        'testsDrivenByIDE': False,
        'testsMustRunOnMainThread': True,
        'testsToRun': None,
        'testsToSkip': None,
        'treatMissingBaselinesAsFailures': False,
        'userAttachmentLifetime': 1
    }

    def __init__(self, kv: dict):
        # self._kv = kv
        assert 'testBundleURL' in kv and isinstance(kv['testBundleURL'], NSURL)
        assert 'sessionIdentifier' in kv and isinstance(
            kv['sessionIdentifier'], uuid.UUID)

        self._kv = copy.deepcopy(self._default)
        self._kv.update(kv)

    def __str__(self):
        return f"XCTestConfiguration({self._kv})"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        return self._kv == other._kv

    def __setitem__(self, key: str, val):
        assert isinstance(key, str)
        self._kv[key] = val

    def encode_archive(objects, archive):
        for (k, v) in objects._kv.items():
            archive.encode(k, v)

    # def decode(objects: list, archive: dict):
    #     # info = ns_info.copy()
    #     # info.pop("$class")
    #     # for key in info.keys():
    #     #     idx = info[key]
    #     #     if isinstance(idx, uid):
    #     #         info[key] = _parse_object(objects, idx.data)
    #     return XCTestConfiguration()


class XCActivityRecord(dict):
    _keys = ('activityType', 'attachments', 'finish', 'start', 'title', 'uuid')

    def __repr__(self):
        attrs = []
        for key in self._keys:
            attrs.append('{}={}'.format(key, self[key]))

        return 'XCActivityRecord({})'.format(', '.join(attrs))

    def decode_archive(archive):
        ret = XCActivityRecord()
        for key in XCActivityRecord._keys:
            ret[key] = archive.decode(key)
        return ret


class NSUUID(uuid.UUID):
    def encode_archive(objects, archive):
        archive._archive_obj["NS.uuidbytes"] = objects.bytes
        # archive.encode("NS.uuidbytes", objects.bytes)

    def decode_archive(archive):
        uuidbytes = archive.decode('NS.uuidbytes')
        return NSUUID(bytes=bytes(uuidbytes))


class uid(int):
    """
    An unique identifier used by Cocoa's NSArchiver to identify a particular
    class that should be used to map an archived object back into a native
    object.
    """

    def __repr__(self):
        return f"uid({int(self)})"

    def __str__(self):
        return f"uid({int(self)})"


class FillType(object):
    """A class for 'Fill', whatever that means."""

    def __repr__(self):
        return 'Fill'


class unicode(str):
    """A class for 'Fill', whatever that means."""

    def __repr__(self):
        return self


Fill = FillType()


@dataclasses.dataclass()
class NSMutableData(DataclassArchiver):
    NSdata: Optional[bytes] = None

    def __repr__(self):
        return "NSMutableData(%s bytes)" % (
            'null' if self.NSdata is None else len(self.NSdata))
