import math
from dataclasses import dataclass, field


@dataclass
class Message:
    timestamp: float
    value: float


@dataclass
class Channel:
    name: str
    units: str = ""
    decimals: int = 0
    messages: list[Message] = field(default_factory=list)

    def start(self) -> float:
        if not self.messages:
            return 0.0
        return self.messages[0].timestamp

    def end(self) -> float:
        if not self.messages:
            return 0.0
        return self.messages[-1].timestamp

    def add_message(self, timestamp: float, value: float) -> None:
        self.messages.append(Message(float(timestamp), float(value)))
        value_text = f"{float(value):f}".rstrip("0").rstrip(".")
        if "." in value_text:
            decimals_present = len(value_text.split(".", 1)[1])
            self.decimals = max(self.decimals, decimals_present)

    def resample(self, start_time: float, end_time: float, frequency_hz: float) -> None:
        if not self.messages:
            return
        if frequency_hz <= 0:
            raise ValueError("frequency_hz must be greater than 0")

        dt_step = 1.0 / frequency_hz
        num_msgs = max(1, int(math.floor(frequency_hz * (end_time - start_time))) + 1)

        value = 0.0
        current_msgs_index = 0
        t = start_time
        new_messages: list[Message] = []

        for _ in range(num_msgs):
            while current_msgs_index < len(self.messages):
                msg_stamp = self.messages[current_msgs_index].timestamp
                if msg_stamp < t + 0.5 * dt_step:
                    value = self.messages[current_msgs_index].value
                    current_msgs_index += 1
                else:
                    break
            new_messages.append(Message(t, value))
            t += dt_step

        if new_messages[-1].timestamp < end_time:
            new_messages.append(Message(end_time, value))

        self.messages = new_messages


@dataclass
class DataLog:
    name: str = ""
    channels: dict[str, Channel] = field(default_factory=dict)

    def clear(self) -> None:
        self.channels = {}

    def add_sample(
        self,
        channel_name: str,
        timestamp: float,
        value: float,
        units: str = "",
    ) -> None:
        channel = self.channels.get(channel_name)
        if channel is None:
            channel = Channel(name=channel_name, units=units)
            self.channels[channel_name] = channel
        channel.add_message(timestamp, value)

    def start(self) -> float:
        start_time = math.inf
        for channel in self.channels.values():
            if channel.messages:
                start_time = min(start_time, channel.start())
        if start_time == math.inf:
            return 0.0
        return start_time

    def end(self) -> float:
        end_time = 0.0
        for channel in self.channels.values():
            if channel.messages:
                end_time = max(end_time, channel.end())
        return end_time

    def duration(self) -> float:
        return self.end() - self.start()

    def resample(self, frequency_hz: float) -> None:
        start_time = self.start()
        end_time = self.end()
        for channel in self.channels.values():
            channel.resample(start_time, end_time, frequency_hz)
