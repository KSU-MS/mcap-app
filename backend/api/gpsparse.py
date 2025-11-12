from mcap_protobuf.decoder import DecoderFactory
from mcap.reader import make_reader


class GpsParser:
    @staticmethod
    def parse_gps(path):
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
        
        print(f"Debug: Starting GPS parse for file: {path}")
        
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
                        print(f"Debug: Processing first GPS message")
                        try:
                            if hasattr(proto_msg, 'DESCRIPTOR'):
                                field_names = [field.name for field in proto_msg.DESCRIPTOR.fields]
                                print(f"Debug: Available protobuf fields: {field_names}")
                        except Exception as e:
                            print(f"Debug: Could not get fields from DESCRIPTOR: {e}")
                    
                    # Extract latitude and longitude from proto_msg
                    try:
                        if hasattr(proto_msg, 'evelogger_vectornav_latitude') and hasattr(proto_msg, 'evelogger_vectornav_longitude'):
                            lat_val = proto_msg.evelogger_vectornav_latitude
                            lon_val = proto_msg.evelogger_vectornav_longitude
                            
                            # Print raw values for first message only
                            if message_count == 1:
                                print(f"Debug: Raw values (first msg) - lat: {lat_val} (type: {type(lat_val)}), lon: {lon_val} (type: {type(lon_val)})")
                            
                            lat_float = float(lat_val)
                            lon_float = float(lon_val)
                            
                            # Skip if coordinates are 0.0, 0.0 (likely default/unset values)
                            if lat_float == 0.0 and lon_float == 0.0:
                                zero_count += 1
                                # Sample messages at intervals to check for non-zero values
                                if message_count % 1000 == 0:
                                    print(f"Debug: Checked {message_count} messages, {valid_count} valid coordinates collected so far...")
                                continue
                            
                            # Store first valid coordinate for backward compatibility
                            if latitude is None and longitude is None:
                                latitude = lat_float
                                longitude = lon_float
                                print(f"Debug: Found first valid GPS coordinates at message #{message_count} - Latitude: {latitude}, Longitude: {longitude}")
                            
                            # Add to all_coordinates list as [longitude, latitude] for GeoJSON/Leaflet compatibility
                            all_coordinates.append([lon_float, lat_float])
                            valid_count += 1
                            
                            # Progress update for large files
                            if valid_count % 1000 == 0:
                                print(f"Debug: Collected {valid_count} valid GPS coordinates...")
                                
                    except Exception as e:
                        if message_count == 1:
                            print(f"Debug: Error extracting GPS values: {e}")
                            import traceback
                            traceback.print_exc()
                
                if message_count == 0:
                    print("Debug: No messages found on topic 'evelogger_vectornav_position_data'")
                elif valid_count == 0:
                    print(f"Debug: Processed {message_count} messages, {zero_count} with (0.0, 0.0) coordinates - no valid GPS coordinates found")
                else:
                    print(f"Debug: Collected {valid_count} valid GPS coordinates from {message_count} messages")
                        
        except Exception as e:
            # If topic doesn't exist or parsing fails, return None values
            print(f"Debug: Error parsing GPS: {str(e)}")
            import traceback
            traceback.print_exc()
        
        print(f"Debug: GPS parse result - First coordinate: ({latitude}, {longitude}), Total coordinates: {len(all_coordinates)}")
        return {
            "latitude": latitude,
            "longitude": longitude,
            "all_coordinates": all_coordinates
        }

