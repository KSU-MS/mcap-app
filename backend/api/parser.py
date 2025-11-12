#this is just a test before writing the api 
#so the goal is to just parse the mcap summary , which will give all the avilable channels , and also the time length of the log and maybe file size 
#final boss also parse the gps cords and , time , and date

#/Users/pettruskonnoth/Documents/mcap_logs/08_14_2025_23_10_40-rec.mcap

import sys
from mcap_protobuf.decoder import DecoderFactory
from mcap.reader import make_reader
import datetime

class Parser:
    @staticmethod
    def parse_stuff(path):
        with open(path, "rb") as f:
            reader = make_reader(f, decoder_factories=[DecoderFactory()])
            summary = reader.get_summary()
            available_channels = summary.channels
            
            # Get channels list
            channels = []
            for value in available_channels.values():
                dict_to_val = str(value)
                split_channel = dict_to_val.split("topic='")[1]
                topic = split_channel.split("'")[0]
                channels.append(topic)

            # Get timestamps and duration
            msg_start = (summary.statistics.message_start_time)/(1e9)
            msg_end = (summary.statistics.message_end_time)/(1e9)
            duration = msg_end - msg_start
            date = datetime.datetime.fromtimestamp(int(msg_start)).strftime('%Y-%m-%d %H:%M:%S')

            # Parse GPS coordinates from vectornav_position_data
            latitude = None
            longitude = None
            try:
                message_count = 0
                for schema, channel, message, proto_msg in reader.iter_decoded_messages(topics="evelogger_vectornav_position_data"):
                    message_count += 1
                    # Debug: Print available attributes to understand the structure (first message only)
                    if message_count == 1:
                        # Get all field names from the protobuf message
                        if hasattr(proto_msg, 'DESCRIPTOR'):
                            field_names = [field.name for field in proto_msg.DESCRIPTOR.fields]
                            print(f"Debug: Available protobuf fields: {field_names}")
                    
                    # Try to extract latitude and longitude from the protobuf message
                    # Common field names: latitude, longitude, lat, lon, position_lat, position_lon
                    if hasattr(proto_msg, 'latitude') and hasattr(proto_msg, 'longitude'):
                        latitude = float(proto_msg.latitude)
                        longitude = float(proto_msg.longitude)
                        break
                    elif hasattr(proto_msg, 'lat') and hasattr(proto_msg, 'lon'):
                        latitude = float(proto_msg.lat)
                        longitude = float(proto_msg.lon)
                        break
                    elif hasattr(proto_msg, 'position_lat') and hasattr(proto_msg, 'position_lon'):
                        latitude = float(proto_msg.position_lat)
                        longitude = float(proto_msg.position_lon)
                        break
                    # Try more field variations
                    elif hasattr(proto_msg, 'Latitude') and hasattr(proto_msg, 'Longitude'):
                        latitude = float(proto_msg.Latitude)
                        longitude = float(proto_msg.Longitude)
                        break
                    elif hasattr(proto_msg, 'gps_lat') and hasattr(proto_msg, 'gps_lon'):
                        latitude = float(proto_msg.gps_lat)
                        longitude = float(proto_msg.gps_lon)
                        break
                    # If the message has a nested structure, try common patterns
                    elif hasattr(proto_msg, 'position'):
                        pos = proto_msg.position
                        if hasattr(pos, 'latitude') and hasattr(pos, 'longitude'):
                            latitude = float(pos.latitude)
                            longitude = float(pos.longitude)
                            break
                    # Try accessing via message descriptor
                    elif hasattr(proto_msg, 'DESCRIPTOR'):
                        # Try to find any field containing 'lat' or 'lon'
                        for field in proto_msg.DESCRIPTOR.fields:
                            field_name = field.name.lower()
                            if 'lat' in field_name and latitude is None:
                                try:
                                    latitude = float(getattr(proto_msg, field.name))
                                except:
                                    pass
                            if 'lon' in field_name and longitude is None:
                                try:
                                    longitude = float(getattr(proto_msg, field.name))
                                except:
                                    pass
                        if latitude is not None and longitude is not None:
                            break
            except Exception as e:
                # If GPS parsing fails, continue without GPS data
                # Uncomment to debug: print(f"GPS parsing error: {e}")
                pass

            # Return data as dictionary
            return {
                "channels": channels,
                "channel_count": len(channels),
                "start_time": msg_start,
                "end_time": msg_end,
                "duration": duration,
                "formatted_date": date,
                "latitude": latitude,
                "longitude": longitude
            }

"""
class Parser():

    def parse_stuff(path):
        with open(path,"rb") as f:
            reader = make_reader(f,decoder_factories=[DecoderFactory()])
            summmary = reader.get_summary()
            avilable_channels = summmary.channels
            print("balls\n")

            count = 0
            #for loop the get the channels from dict
            for value in avilable_channels.values():
                #splitting just the channel
                dictToval = str(value)
                split_channel = dictToval.split("topic='")[1]
                topic = split_channel.split("'")[0]
                print(topic)
                count+=1
            print(f"\nNumber of channels:{count}\n")


            msg_start = (summmary.statistics.message_start_time)/(1e9)
            end = (summmary.statistics.message_end_time)/(1e9)

            duration = end - msg_start

            log_duration = str(datetime.timedelta)

            date = datetime.datetime.fromtimestamp(int(msg_start)).strftime('%Y-%m-%d %H:%M:%S')
            print(date)
            

            print(f"unix time stamp {msg_start} in seconds")

            #for schema , channel , message , proto_msg in reader.iter_decoded_messages(topics="evelogger_vectornav_position_data"):
                #print(proto_msg)
        


#path = "/Users/pettruskonnoth/Documents/mcap_logs/09_25_2025_23_38_08-rec.mcap"


"""