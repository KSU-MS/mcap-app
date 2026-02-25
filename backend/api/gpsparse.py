from mcap_protobuf.decoder import DecoderFactory
from mcap.reader import make_reader


class GpsParser:
    @staticmethod
    def parse_gps(path, sample_step: int = 10):
        """
        Parse GPS coordinates from MCAP file.
        Iterates through messages on 'evelogger_vectornav_position_data' topic
        and extracts all valid latitude/longitude pairs.

        Args:
            path: Path to the MCAP file

        Returns:
            dict with:
            - 'latitude' and 'longitude' keys for the first valid coordinate (for backward compatibility)
            - 'all_coordinates' key with list of [longitude, latitude] pairs for map preview
        """
        latitude = None
        longitude = None
        all_coordinates = []
        sample_step = max(1, int(sample_step))
        last_valid_point = None
        print(f"[parse_gps] Starting GPS parse: {path}")

        try:
            with open(path, "rb") as f:
                reader = make_reader(f, decoder_factories=[DecoderFactory()])

                message_count = 0
                zero_count = 0
                valid_count = 0
                # Iterate through messages on the GPS topic
                for schema, channel, message, proto_msg in reader.iter_decoded_messages(
                    topics="evelogger_vectornav_position_data"
                ):
                    message_count += 1

                    # Only print detailed debug for first message
                    if message_count == 1:
                        print("[parse_gps] Processing first GPS message")
                        try:
                            if hasattr(proto_msg, "DESCRIPTOR"):
                                field_names = [
                                    field.name for field in proto_msg.DESCRIPTOR.fields
                                ]
                                print(
                                    f"[parse_gps] Available protobuf fields: {field_names}"
                                )
                        except Exception as e:
                            print(
                                f"[parse_gps] Could not get fields from DESCRIPTOR: {e}"
                            )

                    # Extract latitude and longitude from proto_msg
                    try:
                        if hasattr(
                            proto_msg, "evelogger_vectornav_latitude"
                        ) and hasattr(proto_msg, "evelogger_vectornav_longitude"):
                            lat_val = proto_msg.evelogger_vectornav_latitude
                            lon_val = proto_msg.evelogger_vectornav_longitude

                            # Print raw values for first message only
                            if message_count == 1:
                                print(
                                    f"[parse_gps] Raw first values - lat: {lat_val} ({type(lat_val)}), lon: {lon_val} ({type(lon_val)})"
                                )

                            lat_float = float(lat_val)
                            lon_float = float(lon_val)

                            # Skip if coordinates are 0.0, 0.0 (likely default/unset values)
                            if lat_float == 0.0 and lon_float == 0.0:
                                zero_count += 1
                                continue

                            # Store first valid coordinate for backward compatibility
                            if latitude is None and longitude is None:
                                latitude = lat_float
                                longitude = lon_float
                                print(
                                    f"[parse_gps] First valid coordinate at message #{message_count}: lat={latitude}, lon={longitude}"
                                )

                            # Add to all_coordinates list as [longitude, latitude] for GeoJSON/Leaflet compatibility
                            point = [lon_float, lat_float]
                            if valid_count == 0 or (valid_count % sample_step == 0):
                                all_coordinates.append(point)
                            last_valid_point = point
                            valid_count += 1

                    except Exception as e:
                        if message_count == 1:
                            print(f"[parse_gps] Error extracting first GPS values: {e}")
                            import traceback

                            traceback.print_exc()

                if message_count == 0:
                    print(
                        "[parse_gps] No messages found on topic 'evelogger_vectornav_position_data'"
                    )
                elif valid_count == 0:
                    print(
                        f"[parse_gps] No valid coordinates. Processed={message_count}, zero_zero={zero_count}"
                    )
                else:
                    if last_valid_point and (
                        not all_coordinates or all_coordinates[-1] != last_valid_point
                    ):
                        all_coordinates.append(last_valid_point)
                    print(
                        f"[parse_gps] Completed GPS parse: valid={valid_count}, stored={len(all_coordinates)}, sample_step={sample_step}, total_messages={message_count}, zero_zero={zero_count}"
                    )

        except Exception as e:
            # If topic doesn't exist or parsing fails, return None values
            print(f"[parse_gps] Error parsing GPS: {str(e)}")
            import traceback

            traceback.print_exc()

        print(
            f"[parse_gps] Result: first_coordinate=({latitude}, {longitude}), stored_coordinates={len(all_coordinates)}"
        )
        return {
            "latitude": latitude,
            "longitude": longitude,
            "all_coordinates": all_coordinates,
        }
