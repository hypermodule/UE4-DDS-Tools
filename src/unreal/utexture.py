'''Classes for texture assets (.uexp and .ubulk)'''
from io import IOBase

import io_util
from .umipmap import Umipmap
from .version import VersionInfo
from directx.dds import DDSHeader, DDS
from directx.dxgi_format import DXGI_FORMAT, DXGI_BYTE_PER_PIXEL


# Defined in UnrealEngine/Engine/Source/Runtime/D3D12RHI/Private/D3D12RHI.cpp
PF_TO_DXGI = {
    'PF_DXT1': DXGI_FORMAT.DXGI_FORMAT_BC1_UNORM,
    'PF_DXT3': DXGI_FORMAT.DXGI_FORMAT_BC2_UNORM,
    'PF_DXT5': DXGI_FORMAT.DXGI_FORMAT_BC3_UNORM,
    'PF_BC4': DXGI_FORMAT.DXGI_FORMAT_BC4_UNORM,
    'PF_BC5': DXGI_FORMAT.DXGI_FORMAT_BC5_UNORM,
    'PF_BC6H': DXGI_FORMAT.DXGI_FORMAT_BC6H_UF16,
    'PF_BC7': DXGI_FORMAT.DXGI_FORMAT_BC7_UNORM,
    'PF_A1': DXGI_FORMAT.DXGI_FORMAT_R1_UNORM,
    'PF_A8': DXGI_FORMAT.DXGI_FORMAT_A8_UNORM,
    'PF_G8': DXGI_FORMAT.DXGI_FORMAT_R8_UNORM,
    'PF_R8': DXGI_FORMAT.DXGI_FORMAT_R8_UNORM,
    'PF_R8G8': DXGI_FORMAT.DXGI_FORMAT_R8G8_UNORM,
    'PF_G16': DXGI_FORMAT.DXGI_FORMAT_R16_UNORM,
    'PF_G16R16': DXGI_FORMAT.DXGI_FORMAT_R16G16_UNORM,
    'PF_B8G8R8A8': DXGI_FORMAT.DXGI_FORMAT_B8G8R8A8_UNORM,
    'PF_A2B10G10R10': DXGI_FORMAT.DXGI_FORMAT_R10G10B10A2_UNORM,
    'PF_A16B16G16R16': DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_UNORM,
    'PF_FloatRGB': DXGI_FORMAT.DXGI_FORMAT_R11G11B10_FLOAT,
    'PF_FloatR11G11B10': DXGI_FORMAT.DXGI_FORMAT_R11G11B10_FLOAT,
    'PF_FloatRGBA': DXGI_FORMAT.DXGI_FORMAT_R16G16B16A16_FLOAT,
    'PF_A32B32G32R32F': DXGI_FORMAT.DXGI_FORMAT_R32G32B32A32_FLOAT,
    'PF_B5G5R5A1_UNORM': DXGI_FORMAT.DXGI_FORMAT_B5G5R5A1_UNORM,
    'PF_ASTC_4x4': DXGI_FORMAT.DXGI_FORMAT_ASTC_4X4_UNORM
}

PF_TO_UNCOMPRESSED = {
    'PF_DXT1': 'PF_B8G8R8A8',
    'PF_DXT3': 'PF_B8G8R8A8',
    'PF_DXT5': 'PF_B8G8R8A8',
    'PF_BC4': 'PF_G8',
    'PF_BC5': 'PF_R8G8',
    'PF_BC6H': 'PF_FloatRGBA',
    'PF_BC7': 'PF_B8G8R8A8',
    'PF_ASTC_4x4': 'PF_B8G8R8A8'
}


def is_power_of_2(n):
    if n == 1:
        return True
    if n % 2 != 0:
        return False
    return is_power_of_2(n // 2)


class Utexture:
    """
    A texture (FTexturePlatformData)

    Notes:
        UnrealEngine/Engine/Source/Runtime/Engine/Classes/Engine/Texture.h
        UnrealEngine/Engine/Source/Runtime/Engine/Private/TextureDerivedData.cpp
    """

    verison: VersionInfo
    name_list: list[str]
    is_light_map: bool
    dxgi_format: DXGI_FORMAT

    def __init__(self, uasset, verbose=False, is_light_map=False):
        self.uasset = uasset
        self.version = uasset.version
        self.name_list = uasset.name_list
        self.is_light_map = is_light_map

        # read .uexp
        f = self.uasset.get_uexp_io(rb=True)
        self.__read_uexp(f)

        # read .ubulk if exists
        if self.has_ubulk:
            f = self.uasset.get_ubulk_io(rb=True)
            for mip in self.mipmaps:
                if mip.is_uexp:
                    continue
                mip.data = f.read(mip.data_size)

        self.print(verbose)

    def __read_uexp(self, f: IOBase):
        start_offset = f.tell()

        # Each UObject has some properties (Imported size, GUID, etc.) before the strip flags.
        # We will skip them cause we don't need to edit them.
        err_offset = min(io_util.get_size(f) - 7, start_offset + 1000)
        while (True):
            """ Serach and skip to \x01\x00\x01\x00\x01\x00\x00\x00.
            \x01\x00 is StripFlags for UTexture
            \x01\x00 is StripFlags for UTexture2D (or Cube)
            \x01\x00\x00\x00 is bCooked for UTexture2D (or Cube)

            Just searching x01 is not the best algorithm but fast enough.
            Because "found 01" means "found strip flags" for most texture assets.
            """
            b = f.read(1)
            while (b != b'\x01'):
                b = f.read(1)
                if (f.tell() >= err_offset):
                    raise RuntimeError('Parse Failed. Make sure you specified UE4 version correctly.')

            if f.read(7) == b'\x00\x01\x00\x01\x00\x00\x00':
                # Found \x01\x00\x01\x00\x01\x00\x00\x00
                break
            else:
                f.seek(-7, 1)

        s = f.tell() - start_offset
        f.seek(start_offset)
        self.unk = f.read(s)

        # UTexture::SerializeCookedPlatformData
        self.pixel_format_name_id = io_util.read_uint64(f)
        self.skip_offset_location = f.tell()  # offset to self.skip_offset
        self.skip_offset = io_util.read_uint32(f)  # Offset to the end of this object
        if self.version >= '4.20':
            io_util.read_null(f)  # ?
        if self.version >= '5.0':
            self.placeholder = f.read(16)  # PlaceholderDerivedData

        # FTexturePlatformData::SerializeCooked (SerializePlatformData)
        self.original_width = io_util.read_uint32(f)
        self.original_height = io_util.read_uint32(f)
        self.__read_packed_data(io_util.read_uint32(f))  # PlatformData->PackedData
        self.__update_format(io_util.read_str(f))  # PixelFormatString

        if self.version == 'ff7r' and self.has_opt_data:
            io_util.read_null(f)
            io_util.read_null(f)
            f.seek(4, 1)  # NumMipsInTail ? (bulk map num + first_mip_to_serialize)

        self.first_mip_to_serialize = io_util.read_uint32(f)
        map_num = io_util.read_uint32(f)  # mip map count

        if self.version == 'ff7r':
            # ff7r have all mipmap data in a mipmap object
            self.uexp_optional_mip = Umipmap.read(f, self.version)
            io_util.read_const_uint32(f, self.num_slices)
            f.seek(4, 1)  # uexp mip map num

        # read mipmaps
        self.mipmaps = [Umipmap.read(f, self.version) for i in range(map_num)]

        _, ubulk_map_num = self.get_mipmap_num()
        self.has_ubulk = ubulk_map_num > 0

        if self.version >= '4.23':
            # bIsVirtual
            io_util.read_null(f, msg='Virtual texture is unsupported.')
        self.none_name_id = io_util.read_uint64(f)

        if self.is_light_map:
            self.light_map_flags = io_util.read_uint32(f)  # ELightMapFlags

        self.uexp_size = f.tell() - start_offset

        if self.version == 'ff7r' and self.has_supported_format():
            # split mipmap data
            i = 0
            for mip in self.mipmaps:
                if mip.is_uexp:
                    size = int(mip.pixel_num * self.byte_per_pixel * self.num_slices)
                    mip.data = self.uexp_optional_mip.data[i: i + size]
                    i += size
            io_util.check(i, len(self.uexp_optional_mip.data))

    def get_max_uexp_size(self) -> tuple[int, int]:
        """Get max size of uexp mips."""
        for mip in self.mipmaps:
            if mip.is_uexp:
                break
        return mip.width, mip.height

    def get_max_size(self) -> tuple[int, int]:
        """Get max size of mips."""
        return self.mipmaps[0].width, self.mipmaps[0].height

    def get_mipmap_num(self) -> tuple[int, int]:
        uexp_map_num = 0
        ubulk_map_num = 0
        for mip in self.mipmaps:
            uexp_map_num += mip.is_uexp
            ubulk_map_num += not mip.is_uexp
        return uexp_map_num, ubulk_map_num

    def write(self, valid=False):
        # write .uexp
        f = self.uasset.get_uexp_io(rb=False)
        if self.has_ubulk:
            ubulk_io = self.uasset.get_ubulk_io(rb=False)
            ubulk_start_offset = ubulk_io.tell()
        else:
            ubulk_start_offset = 0
        self.__write_uexp(f, ubulk_start_offset, valid=valid)

        # write .ubulk if exists
        if self.has_ubulk:
            for mip in self.mipmaps:
                if not mip.is_uexp:
                    ubulk_io.write(mip.data)

    def __write_uexp(self, f: IOBase, ubulk_start_offset: int, valid=False):
        uasset_size = self.uasset.get_size()
        start_offset = f.tell()

        # get mipmap info
        max_width, max_height = self.get_max_uexp_size()
        uexp_map_num, ubulk_map_num = self.get_mipmap_num()
        uexp_map_data_size = 0
        for mip in self.mipmaps:
            if mip.is_uexp:
                uexp_map_data_size += len(mip.data) + 32 * (self.version != 'ff7r')

        if not valid:
            self.original_height = max_height
            self.original_width = max_width

        f.write(self.unk)

        # write meta data
        io_util.write_uint64(f, self.pixel_format_name_id)
        self.skip_offset_location = f.tell()
        f.seek(4, 1)  # for self.skip_offset. write here later
        if self.version >= '4.20':
            io_util.write_null(f)
        if self.version >= '5.0':
            f.write(self.placeholder)

        io_util.write_uint32(f, self.original_width)
        io_util.write_uint32(f, self.original_height)
        io_util.write_uint32(f, self.__get_packed_data())

        io_util.write_str(f, self.pixel_format)

        if self.version == 'ff7r' and self.has_opt_data:
            io_util.write_null(f)
            io_util.write_null(f)
            io_util.write_uint32(f, ubulk_map_num + self.first_mip_to_serialize)

        io_util.write_uint32(f, self.first_mip_to_serialize)
        io_util.write_uint32(f, len(self.mipmaps))

        if self.version == 'ff7r':
            # pack mipmaps in a mipmap object
            uexp_bulk = b''
            for mip in self.mipmaps:
                mip.meta = True
                if mip.is_uexp:
                    uexp_bulk = b''.join([uexp_bulk, mip.data])
            size = self.get_max_uexp_size()
            self.uexp_optional_mip = Umipmap(self.version)
            self.uexp_optional_mip.update(uexp_bulk, size, True)
            self.uexp_optional_mip.write(f, uasset_size)

            io_util.write_uint32(f, self.num_slices)
            io_util.write_uint32(f, uexp_map_num)

        ubulk_offset = ubulk_start_offset

        # write mipmaps
        for mip in self.mipmaps:
            if not mip.is_uexp:
                mip.offset = ubulk_offset
                ubulk_offset += mip.data_size
            mip.write(f, uasset_size)

        if self.version >= '4.23':
            io_util.write_null(f)

        if self.version >= '5.0':
            self.skip_offset = f.tell() - self.skip_offset_location
        else:
            self.skip_offset = f.tell() + uasset_size
        io_util.write_uint64(f, self.none_name_id)

        if self.is_light_map:
            io_util.write_uint32(f, self.light_map_flags)

        current = f.tell()
        f.seek(self.skip_offset_location)
        io_util.write_uint32(f, self.skip_offset)
        f.seek(current)
        self.uexp_size = current - start_offset

    def rewrite_offset_data(self):
        if self.version <= '4.15' or self.version >= '4.26' or self.version == 'ff7r':
            return
        # ubulk mipmaps have wierd offset data. (Fixed at 4.26)
        f = self.uasset.get_uexp_io(rb=False)
        uasset_size = self.uasset.get_size()
        uexp_size = self.uasset.get_uexp_size()
        ubulk_offset_base = -uasset_size - uexp_size
        for mip in self.mipmaps:
            if not mip.is_uexp:
                mip.rewrite_offset(f, ubulk_offset_base + mip.offset)

    def remove_mipmaps(self):
        old_mipmap_num = len(self.mipmaps)
        if old_mipmap_num == 1:
            return
        self.mipmaps = [self.mipmaps[0]]
        self.mipmaps[0].is_uexp = True
        self.has_ubulk = False
        print('mipmaps have been removed.')
        print(f'  mipmap: {old_mipmap_num} -> 1')

    def get_dds(self) -> DDS:
        """Get texture as dds."""
        if not self.has_supported_format():
            raise RuntimeError(f'Unsupported pixel format. ({self.pixel_format})')

        # make dds header
        header = DDSHeader()
        header.update(0, 0, 0, self.dxgi_format, self.is_cube)

        mipmap_data = []
        mipmap_size = []

        # get mipmaps
        for mip in self.mipmaps:
            mipmap_data.append(mip.data)
            mipmap_size.append([mip.width, mip.height])

        # update header
        header.width, header.height = self.get_max_size()
        header.mipmap_num = len(mipmap_data)

        return DDS(header, mipmap_data, mipmap_size)

    def inject_dds(self, dds: DDS):
        """Inject dds into asset."""
        if not self.has_supported_format():
            raise RuntimeError(f'Unsupported pixel format. ({self.pixel_format})')

        # check formats
        if dds.header.dxgi_format != self.dxgi_format:
            raise RuntimeError(
                "The format does not match. "
                f"(Uasset: {self.dxgi_format.name[12:]}, DDS: {dds.header.dxgi_format.name[12:]})"
            )

        if dds.is_cube() != self.is_cube:
            raise RuntimeError(
                "Texture type does not match. "
                f"(Uasset: {self.get_texture_type()}, DDS: {dds.get_texture_type()})"
            )

        max_width, max_height = self.get_max_size()
        old_size = (max_width, max_height)
        old_mipmap_num = len(self.mipmaps)

        uexp_width, uexp_height = self.get_max_uexp_size()

        # inject
        self.first_mip_to_serialize = 0
        i = 0
        self.mipmaps = [Umipmap(self.version) for i in range(len(dds.mipmap_data))]
        for data, size, mip in zip(dds.mipmap_data, dds.mipmap_size, self.mipmaps):
            if self.has_ubulk and i + 1 < len(dds.mipmap_data) and size[0] * size[1] > uexp_width * uexp_height:
                mip.update(data, size, False)
            else:
                mip.update(data, size, True)
            i += 1

        # print results
        max_width, max_height = self.get_max_size()
        new_size = (max_width, max_height)
        _, ubulk_map_num = self.get_mipmap_num()
        if ubulk_map_num == 0:
            self.has_ubulk = False
        if self.version == "ff7r":
            self.has_opt_data = self.has_ubulk
        new_mipmap_num = len(self.mipmaps)

        print('DDS has been injected.')
        print(f'  size: {old_size} -> {new_size}')
        print(f'  mipmap: {old_mipmap_num} -> {new_mipmap_num}')

        # warnings
        if new_mipmap_num > 1 and (not is_power_of_2(max_width) or not is_power_of_2(max_height)):
            print(f'Warning: Mipmaps should have power of 2 as its width and height. ({max_width}, {max_height})')
        if new_mipmap_num > 1 and old_mipmap_num == 1:
            print('Warning: The original texture has only 1 mipmap. But your dds has multiple mipmaps.')

    def print(self, verbose=False):
        if verbose:
            i = 0
            for mip in self.mipmaps:
                print(f'  Mipmap {i}')
                mip.print(padding=4)
                i += 1
        max_width, max_height = self.get_max_size()
        print(f'  width: {max_width}')
        print(f'  height: {max_height}')
        print(f'  format: {self.pixel_format} ({self.dxgi_format.name[12:]})')
        print(f'  mipmaps: {len(self.mipmaps)}')
        print(f'  cubemap: {self.is_cube}')

    def to_uncompressed(self):
        if self.pixel_format in PF_TO_UNCOMPRESSED:
            self.change_format(PF_TO_UNCOMPRESSED[self.pixel_format])

    def change_format(self, pixel_format: str):
        """Change pixel format."""
        if self.pixel_format != pixel_format:
            print(f'Changed pixel format from {self.pixel_format} to {pixel_format}')
        self.__update_format(pixel_format)
        self.uasset.update_name_list(self.pixel_format_name_id, pixel_format)

    def has_supported_format(self):
        return self.pixel_format in PF_TO_DXGI

    def __update_format(self, pixel_format: str):
        self.pixel_format = pixel_format
        if not self.has_supported_format():
            print(f'Warning: Unsupported pixel format. ({self.pixel_format})')
            self.dxgi_format = DXGI_FORMAT.DXGI_FORMAT_UNKNOWN
            self.byte_per_pixel = None
            return
        self.dxgi_format = PF_TO_DXGI[self.pixel_format]
        self.byte_per_pixel = DXGI_BYTE_PER_PIXEL[self.dxgi_format]

    def __read_packed_data(self, packed_data: int):
        self.is_cube = packed_data & (1 << 31) > 0
        self.has_opt_data = packed_data & (1 << 30) > 0
        self.num_slices = packed_data & ((1 << 30) - 1)

    def __get_packed_data(self) -> int:
        packed_data = self.num_slices
        packed_data |= self.is_cube * (1 << 31)
        packed_data |= self.has_opt_data * (1 << 30)
        return packed_data

    def get_texture_type(self) -> str:
        return ['2D', 'Cube'][self.is_cube]

    def has_uexp(self):
        return self.uasset.has_uexp()
