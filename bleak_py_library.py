import asyncio
from datetime import datetime
import json
import os
import threading
import time
import bleak
import paho.mqtt.client as mqtt
import logging

logger = logging.getLogger(__name__)


# MQTT Settings
MQTT_BROKER_HOST = "192.168.12.225"
MQTT_BROKER_PORT = 1883
MQTT_USERNAME = "flotta"  # Replace with your MQTT username
MQTT_PASSWORD = "flotta"  # Replace with your MQTT password

FLOTTA_SQLITE_DB = os.getenv("FLOTTA_SQLITE_DB", "../flotta-device-worker/flotta.db")
PERIODIC_DELAY = os.getenv("PERIODIC_DELAY", 60)


# Global MQTT client
mqtt_client = None

async def connect_or_scan(device_name, device_uuid):
    logger.info("starting scan for device... ")
            
    # If not found in history, perform scanning and connecting
    scanner = bleak.BleakScanner()
    devices = await scanner.discover()
    
    for device in devices:
        try:
            if (device_name is not None and device.name == device_name) or \
               (device_uuid is not None and str(device.address) == device_uuid):
                await connect_and_read_characteristics(device)
                return True
        except Exception as e:
            print(f"Error while scanning/connecting to device: {e}")
    print("device %s: ",device_name," not found")
    return False

async def connect_and_read_characteristics(device):
    async with bleak.BleakClient(device) as client:
        print("HAHAHAH")
        try:
            current_time = datetime.now()
            time_string = current_time.strftime("%Y-%m-%d %H:%M:%S")
            
            
            if client.is_connected:
                await client.disconnect()
            await client.connect()
            print(device.name+"\n")
            print(str(device.address)+"\n")
            # Add connected device to device history
            characteristics_info = []
            connected_device = {
                "wireless_device_name": device.name,
                "wireless_device_manufacturer": None,
                "wireless_device_model": None,
                "wireless_device_sw_version": None,
                "wireless_device_identifier": str(device.address),
                "wireless_device_protocol":"BLE",
                "wireless_device_connection": "BLE",
                "wireless_device_battery": None,
                "wireless_device_availability": None,
                "wireless_device_description": str(device.details),
                "wireless_device_last_seen": time_string,
                "device_properties": characteristics_info
            }
            
            services = await client.get_services()
            
            
            for service in services:
                
                print(service.uuid)
                print("\n service \n")
                
                
                for char in service.characteristics:
                    char_info = {
                        "property_identifier": str(char.uuid),
                        "property_service_uuid": str(service.uuid),
                        "property_name": char.description,
                        
                        
                        "property_access_mode": None,
                        "property_reading": None,
                        "property_state": None,
                        
                        "property_unit": None,
                        "property_description": None,
                        "property_last_seen": time_string,
                        "descriptors": []
                    }
                    
                    
                    if "notify" in char.properties or "read" in char.properties:
                        # print("\n READ \n")
                        
                        try:
                            char_info["property_access_mode"] = "Read"
                            
                            value = await client.read_gatt_char(char.uuid)
                            value_str = value.decode("utf-8")  # Decode the bytearray to a string
                            char_info["property_reading"] = value_str.strip()
                        except Exception as err:
                            logger.error(
                                "  [Characteristic] %s (%s), Error: %s",
                                char,
                                ",".join(char.properties),
                                err,
                            )
                            print(err)

                    elif "write" in char.properties :
                        
                        try:
                            char_info["property_access_mode"] = "ReadWrite"
                            
                            value = await client.read_gatt_char(char.uuid)
                            value_str = value.decode("utf-8")  # Decode the bytearray to a string
                            char_info["property_state"] = value_str.strip()
                        except Exception as err:
                            logger.error(
                                "  [Characteristic] %s (%s), Error: %s",
                                char,
                                ",".join(char.properties),
                                err,
                            )
                            print(err)
                            
                        logger.info(
                            "  [Characteristic] %s (%s)", char, ",".join(char.properties)
                        )

                    for descriptor in char.descriptors:
                        try:
                            descriptor_info = {
                                "descriptor_uuid": str(descriptor.uuid),
                                "descriptor_value": None
                            }
                            
                            # print(descriptor)
                            
                            value2 = await client.read_gatt_descriptor(descriptor.handle)
                            value_str2 = value2.decode("utf-8")
                            logger.info("    [Descriptor] %s, Value: %r", descriptor, value2)
                            descriptor_info["descriptor_uuid"] = descriptor.uuid
                            descriptor_info["descriptor_value"] = value_str2                         
                            char_info["descriptors"].append(descriptor_info)
                            if char_info["property_name"] == "" or char_info["property_name"] == "Unknown":
                                char_info["property_name"] = value_str2
                                
                        except Exception as err:
                            logger.error("    [Descriptor] %s, Error: %s", descriptor, err)
                            print(err)
                    characteristics_info.append(char_info)
            connected_device["device_properties"] = characteristics_info

            mqtt_client.publish("plugin/edge/upstream", json.dumps(connected_device))
        except Exception as e:
            print(f"Error while reading characteristics: {e}")
             
        
def on_message(client, userdata, message):
    print("RECEIVING DATA...........\n")
    print("MQTT Topic: \n", message.topic)  # Print the MQTT topic

    payload = message.payload.decode("utf-8")
    payload_json = json.loads(payload)
    current_time = datetime.now()
    time_string = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
        
    try:
        # payload_json = json.loads(payload)
        # device_name = payload_json.get("wireless_device_name")
        # device_uuid = payload_json.get("wireless_device_identifier")
        
        # if device_name or device_uuid:
        #     asyncio.run(connect_or_scan(device_name, device_uuid))
        # else:
        #     print("Invalid payload format.")
        if message.topic == "cloud/plugin/downstream/ble/devices/verified":
            print("am in the topic")
            for item in payload_json:
                asyncio.run(connect_or_scan(item["wireless_device_identifier"], item["wireless_device_name"]))

    except json.JSONDecodeError:
        print("Invalid JSON payload.")

def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker.")
    client.subscribe("cloud/plugin/downstream/ble")
    client.subscribe("cloud/plugin/downstream/ble/devices/verified")
async def periodic_task():
    while True:
        # time.sleep(PERIODIC_DELAY)  
        # Call your desired function here
        print("Running the periodic task...")
        print("scanning BLE devices for 5 seconds, please wait...")
        
        discovered_unpaired_devices = []
        
        devices = await bleak.BleakScanner.discover(return_adv=True)
        for d, a in devices.values():
            discovered_unpaired_device = {
                "wireless_device_identifier": d.name,
                "wireless_device_name": d.address
            }
            discovered_unpaired_devices.append(discovered_unpaired_device)
        # await asyncio.sleep(PERIODIC_DELAY)  # Wait for 10 seconds before the next iteration
        mqtt_client.publish("plugin/edge/upstream/ble/unpaired", json.dumps(discovered_unpaired_devices)) #prefix should be discovered maybe 
        time.sleep(PERIODIC_DELAY)


def main():
    global mqtt_client
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)  # Set MQTT username and password

    mqtt_client.on_log = lambda client, userdata, level, buf: print(buf)
    mqtt_client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, 60)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    periodic_task_thread = threading.Thread(target=loop.run_until_complete, args=(periodic_task(),))
    periodic_task_thread.daemon = True
    periodic_task_thread.start()

    mqtt_client.loop_forever()
    while True:
        time.sleep(1)
    
if __name__ == "__main__":
    main()
