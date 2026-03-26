import datetime
import struct
from dataclasses import dataclass
from pathlib import Path

from .telemetry_log import DataLog


def _enc(value: str) -> bytes:
    return str(value or "").encode("ascii", errors="ignore")


@dataclass
class _LdVehicle:
    id: str
    weight: int
    vehicle_type: str
    comment: str

    fmt = "<64s128xI32s32s"

    def write(self, file_handle) -> None:
        file_handle.write(
            struct.pack(
                self.fmt,
                _enc(self.id),
                int(self.weight),
                _enc(self.vehicle_type),
                _enc(self.comment),
            )
        )


@dataclass
class _LdVenue:
    name: str
    vehicle_ptr: int
    vehicle: _LdVehicle

    fmt = "<64s1034xH"

    def write(self, file_handle) -> None:
        file_handle.write(struct.pack(self.fmt, _enc(self.name), self.vehicle_ptr))
        if self.vehicle_ptr > 0:
            file_handle.seek(self.vehicle_ptr)
            self.vehicle.write(file_handle)


@dataclass
class _LdEvent:
    name: str
    session: str
    comment: str
    venue_ptr: int
    venue: _LdVenue

    fmt = "<64s64s1024sH"

    def write(self, file_handle) -> None:
        file_handle.write(
            struct.pack(
                self.fmt,
                _enc(self.name),
                _enc(self.session),
                _enc(self.comment),
                self.venue_ptr,
            )
        )
        if self.venue_ptr > 0:
            file_handle.seek(self.venue_ptr)
            self.venue.write(file_handle)


@dataclass
class _LdHead:
    meta_ptr: int
    data_ptr: int
    event_ptr: int
    event: _LdEvent
    driver: str
    vehicle_id: str
    venue: str
    created_at: datetime.datetime
    short_comment: str

    fmt = "<" + ("I4xII20xI24xHHHI8sHHI4x16s16x16s16x64s64s64x64s64x1024xI66x64s126x")

    def write(self, file_handle, channel_count: int) -> None:
        file_handle.write(
            struct.pack(
                self.fmt,
                0x40,
                self.meta_ptr,
                self.data_ptr,
                self.event_ptr,
                1,
                0x4240,
                0xF,
                0x1F44,
                _enc("ADL"),
                420,
                0xADB0,
                channel_count,
                _enc(self.created_at.date().strftime("%d/%m/%Y")),
                _enc(self.created_at.time().strftime("%H:%M:%S")),
                _enc(self.driver),
                _enc(self.vehicle_id),
                _enc(self.venue),
                0xC81A4,
                _enc(self.short_comment),
            )
        )

        if self.event_ptr > 0:
            file_handle.seek(self.event_ptr)
            self.event.write(file_handle)


@dataclass
class _LdChannel:
    prev_meta_ptr: int
    next_meta_ptr: int
    data_ptr: int
    data_len: int
    freq: int
    name: str
    unit: str
    samples: list[float]

    fmt = "<" + ("IIIIHHHHhhhh32s8s12s40x")

    def write_header(self, file_handle, index: int) -> None:
        short_name = self.name[:8]
        file_handle.write(
            struct.pack(
                self.fmt,
                self.prev_meta_ptr,
                self.next_meta_ptr,
                self.data_ptr,
                self.data_len,
                0x2EE1 + index,
                0x07,
                4,
                self.freq,
                0,
                1,
                1,
                0,
                _enc(self.name),
                _enc(short_name),
                _enc(self.unit),
            )
        )

    def write_data(self, file_handle) -> None:
        for sample in self.samples:
            file_handle.write(struct.pack("<f", float(sample)))


class MotecLogNative:
    VEHICLE_PTR = 1762
    VENUE_PTR = 5078
    EVENT_PTR = 8180
    HEADER_PTR = 11336

    def __init__(self, frequency_hz: float):
        if frequency_hz <= 0:
            raise ValueError("frequency_hz must be greater than 0")
        self.frequency_hz = frequency_hz

        self.driver = ""
        self.vehicle_id = ""
        self.vehicle_weight = 0
        self.vehicle_type = ""
        self.vehicle_comment = ""
        self.venue_name = ""
        self.event_name = ""
        self.event_session = ""
        self.long_comment = ""
        self.short_comment = ""
        self.created_at = datetime.datetime.now()

    def write_from_datalog(self, datalog: DataLog, output_path: Path) -> None:
        if not datalog.channels:
            raise RuntimeError("Cannot write LD: no channels in datalog")

        channel_names = list(datalog.channels.keys())
        channel_header_size = struct.calcsize(_LdChannel.fmt)
        meta_start = self.HEADER_PTR
        data_start = meta_start + channel_header_size * len(channel_names)

        channels: list[_LdChannel] = []
        next_data_ptr = data_start
        for idx, channel_name in enumerate(channel_names):
            source_channel = datalog.channels[channel_name]
            sample_values = [message.value for message in source_channel.messages]
            data_len = len(sample_values)
            channel_nbytes = data_len * 4

            meta_ptr = meta_start + idx * channel_header_size
            prev_meta_ptr = 0 if idx == 0 else (meta_ptr - channel_header_size)
            next_meta_ptr = (
                0 if idx == len(channel_names) - 1 else (meta_ptr + channel_header_size)
            )

            channels.append(
                _LdChannel(
                    prev_meta_ptr=prev_meta_ptr,
                    next_meta_ptr=next_meta_ptr,
                    data_ptr=next_data_ptr,
                    data_len=data_len,
                    freq=max(1, int(round(self.frequency_hz))),
                    name=source_channel.name,
                    unit=source_channel.units,
                    samples=sample_values,
                )
            )
            next_data_ptr += channel_nbytes

        vehicle = _LdVehicle(
            id=self.vehicle_id,
            weight=self.vehicle_weight,
            vehicle_type=self.vehicle_type,
            comment=self.vehicle_comment,
        )
        venue = _LdVenue(
            name=self.venue_name, vehicle_ptr=self.VEHICLE_PTR, vehicle=vehicle
        )
        event = _LdEvent(
            name=self.event_name,
            session=self.event_session,
            comment=self.long_comment,
            venue_ptr=self.VENUE_PTR,
            venue=venue,
        )
        head = _LdHead(
            meta_ptr=meta_start,
            data_ptr=data_start,
            event_ptr=self.EVENT_PTR,
            event=event,
            driver=self.driver,
            vehicle_id=self.vehicle_id,
            venue=self.venue_name,
            created_at=self.created_at,
            short_comment=self.short_comment,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as file_handle:
            head.write(file_handle, len(channels))
            if channels:
                file_handle.seek(meta_start)
                for idx, channel in enumerate(channels):
                    channel.write_header(file_handle, idx)
                for channel in channels:
                    file_handle.seek(channel.data_ptr)
                    channel.write_data(file_handle)


def write_ld_native(datalog: DataLog, output_path: Path, frequency_hz: float) -> None:
    writer = MotecLogNative(frequency_hz=frequency_hz)
    writer.write_from_datalog(datalog, output_path)
