from cStringIO import StringIO
from os import SEEK_CUR, SEEK_END
from struct import unpack

class PersonDict(dict):
    """Delete is supported on the pid index only"""
    def __init__(self, *args, **kwargs):
        self._key_map = dict()
        
        if args:
            print args
            for arg in args[0]:
                self[arg[0]] = arg[1]
                
        if kwargs:
            print kwargs
            for key, value in kwargs.iteritems():
                self[key] = value
        
    def __getitem__(self, key):
        if isinstance(key, str):
            key = self._key_map[key]

        return super(PersonDict, self).__getitem__(key)

    def __setitem__(self, key, value):
        if isinstance(key, str):
            self._key_map[key] = value.pid
            key = value.pid
        elif isinstance(key, int):
            self._key_map[value.name] = key
            
        super(PersonDict, self).__setitem__(value.pid, value)

class ByteStream(object):
    def __init__(self, stream):
        self.stream = StringIO(stream)
        self.stream.seek(0, SEEK_END)
        self.length = self.stream.tell()
        self.stream.seek(0)
    
    @property
    def remaining(self):
        return self.length-self.cursor
        
    @property
    def cursor(self):
        return self.stream.tell()
        
    def get_bytes(self, number):
        return self.stream.read(number)
        
    def get_range(self, start, end):
        self.stream.seek(start)
        return self.get_bytes(end-start)
        
    def get_little_bytes(self, number):
        bytes = [self.stream.read(1) for i in range(0,number)]
        return ''.join(reversed(bytes))
        
    def skip(self, number):
        self.stream.read(number)
        
    def peek(self, number):
        bytes = self.stream.read(number)
        self.stream.seek(-number,SEEK_CUR)
        return bytes
        
    def get_string(self, number):
        #This would be easier if I knew the encoding of the bytes
        hex = self.get_hex(number)
        return hex.decode("hex")
        
    def get_hex(self, number):
        bytes = self.stream.read(number)
        return bytes.encode("hex")
        
    def get_big_8(self):
        byte = self.stream.read(1)
        return unpack('B', byte)[0]

    def get_big_16(self):
        bytes = self.stream.read(2)
        return unpack('>H', bytes)[0]

    def get_big_32(self):
        bytes = self.stream.read(4)
        return unpack('>I', bytes)[0]

    def get_big_64(self):
        bytes = self.stream.read(8)
        return unpack('>Q', bytes)[0]

    def get_little_8(self):
        byte = self.stream.read(1)
        return unpack('B', byte)[0]

    def get_little_16(self):
        bytes = self.stream.read(2)
        return unpack('<H', bytes)[0]

    def get_little_32(self):
        bytes = self.stream.read(4)
        return unpack('<I', bytes)[0]

    def get_little_64(self):
        bytes = self.stream.read(8)
        return unpack('<Q', bytes)[0]
        
    def get_count(self):
        #For some reason counts are always doubled
        return self.get_big_8()/2
        
    def get_timestamp(self):
        #The 7-8 bits of the first byte indicate the byte length of
        #the timestamp, shift them off the time and loop through them
        first = self.get_big_8()
        time = first >> 2
        for i in range(0,first & 0x03):
            time = (time << 8) | self.get_big_8()
        
        return time
        
    def get_vlf(self):
        result, count = 0, 0
            
        #Loop through bytes until the first bit is zero
        #build the result by adding new bits to the right
        while(True):
            num = self.get_big_8()
            if num & 0x80 > 0:
                result += (num & 0x7F) << (7*count)
                count = count + 1
            else:
                result += num << (7*count)
                break
        
        #The last bit of the result is a sign flag
        return pow(-1, result & 0x1) * (result >> 1)
        
    def parse_serialized_data(self):
        #The first byte serves as a flag for the type of data to follow
        datatype = self.get_big_8()
                
        if datatype == 0x02:
            #0x02 is a byte string with the first byte indicating
            #the length of the byte string to follow
            data = self.get_hex(self.get_count())
            
        elif datatype == 0x04:
            #0x04 is an serialized data list with first two bytes always 01 00
            #and the next byte indicating the number of elements in the list
            #each element is a serialized data structure
            self.skip(2)    #01 00
            data = [self.parse_serialized_data() for i in range(0, self.get_count())]
            
        elif datatype == 0x05:
            #0x05 is a serialized key,value structure with the first byte
            #indicating the number of key,value pairs to follow
            #When looping through the pairs, the first byte is the key,
            #followed by the serialized data object value
            data, count = dict(), self.get_count()
            for i in range(0,count):
                key,value = self.get_count(), self.parse_serialized_data()
                data[key] = value #Done like this to keep correct parse order
            
        elif datatype == 0x06:
            data = self.get_big_8()
            
        elif datatype == 0x07:
            data = self.get_big_32()
            
        elif datatype == 0x09:
            data = self.get_vlf()
            
        else:
            raise TypeError("Uknown Data Type: '%s'" % datatype)
        
        return data


BIG = 0
LITTLE = 1
from bitstring import ConstBitStream

class SC2Buffer(object):

    def __init__(self, file_contents, endian=BIG):
        if hasattr(file_contents,'read'): #is a file-like object
            file_contents = file_contents.read()
        self.stream = ConstBitStream(hex=file_contents.encode("hex"))
        self.__endian = endian

    def skip(self, bits=0, bytes=0):
        self.stream.pos += bits + bytes*8

    def read_int(self, bits=0, bytes=0, endian=None):
        endian = endian or self.__endian
        bit_count = bits+bytes*8
        if bits!=0:
            return self.stream.read(bit_count).uint
        if endian == BIG:
            return self.stream.read(bit_count).uintbe
        elif endian == LITTLE:
            return self.stream.read(bit_count).uintle
    
    def read_string(self,bytes=None):
        char_count = bytes if bytes!=None else self.read_int(bytes=1)
        chars = self.read_hex(bytes=char_count).decode("hex")
        print len(chars)
        if self.__endian == LITTLE:
            chars = str(reversed(chars))
        return chars

    def byte_align(self):
        self.stream.bytealign()

    def read_count(self):
        return self.read_int(bytes=1)/2

    def read_hex(self, bits=0, bytes=0):
        bit_count = bits+bytes*8
        return self.stream.read(bit_count).hex[2:].upper()

    def read_timestamp(self):
        #The 7-8 bits of the first byte indicate the extra byte count
        time = self.read_int(bits=6)
        count = self.read_int(bits=2)
        for i in range(0,count):
            time = (time << 8) | self.read_int(bytes=1)
        return time

    def read_vlf(self):
        #Loop through bytes until the first bit is zero
        #build the result by adding new bits to the left
        result, count = 0, 0
        while(True):
            flag = self.read_int(bits=1)
            result += self.read_int(bits=7) << (7*count)
            if flag:
                count += 1
            else:
                #The last bit of the result is a sign flag
                return pow(-1, result & 0x1) * (result >> 1)

    def read_serialized_data(self):
        #The first byte serves as a flag for the type of data to follow
        datatype = self.read_int(bytes=1)
        print hex(datatype)
        if datatype == 0x02:
            #0x02 is a byte string with the first byte indicating
            #the length of the byte string to follow
            data = self.read_string(self.read_count())
            print data

        elif datatype == 0x04:
            #0x04 is an serialized data list with first two bytes always 01 00
            #and the next byte indicating the number of elements in the list
            #each element is a serialized data structure
            self.skip(bytes=2)    #01 00
            count = self.read_count()
            data = [self.read_serialized_data() for i in range(0, count)]
            print data

        elif datatype == 0x05:
            #0x05 is a serialized key,value structure with the first byte
            #indicating the number of key,value pairs to follow
            #When looping through the pairs, the first byte is the key,
            #followed by the serialized data object value
            data, count = dict(), self.read_count()
            for i in range(0,count):
                key,value = self.read_count(), self.read_serialized_data()
                print "Dict key: %s" % key
                data[key] = value #Done like this to keep correct parse order
            
        elif datatype == 0x06:
            data = self.read_int(bytes=1)
            
        elif datatype == 0x07:
            data = self.read_int(bytes=4)
            
        elif datatype == 0x09:
            data = self.read_vlf()
            
        else:
            raise TypeError("Uknown Data Type: '%s'" % datatype)
        
        return data

    def peek(self, bits=0, bytes=0, format="hex"):
        return self.stream.peek('%s:%s' % (format,bits+bytes*8))

    @property
    def position(self):
        return self.stream.pos

    @property
    def length(self):
        return self.stream.len

    @property
    def remaining(self):
        return (self.stream.len - self.stream.pos)

    @property
    def empty(self):
        return self.remaining == 0


def read_header(file):
    bytes = SC2Buffer(file.read())
    
    #Check the file type for the MPQ header bytes
    if bytes.empty or bytes.read_hex(bytes=4) != '4D50511B':
        raise ValueError("File '%s' is not an MPQ file" % file.name)
    
    #Extract replay header data, we don't actually use this for anything
    max_data_size = bytes.read_int(bytes=4,endian=LITTLE) #possibly data max size
    header_offset = bytes.read_int(bytes=4,endian=LITTLE) #Offset of the second header
    data_size = bytes.read_int(bytes=4,endian=LITTLE)     #possibly data size
    
    #Extract replay attributes from the mpq
    data = bytes.read_serialized_data()
    
    #return the release and frames information
    return data[1],data[3]

def timestamp_from_windows_time(windows_time):
    # This windows timestamp measures the number of 100 nanosecond periods since
    # January 1st, 1601. First we subtract the number of nanosecond periods from
    # 1601-1970, then we divide by 10^7 to bring it back to seconds.
    return (windows_time-116444735995904000)/10**7

import inspect
def key_in_bases(key,bases):
    bases = list(bases)
    for base in list(bases):
        bases.extend(inspect.getmro(base))
    for clazz in set(bases):
        if key in clazz.__dict__: return True
    return False
