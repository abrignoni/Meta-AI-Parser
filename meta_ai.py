# Meta AI - Android companion app (com.facebook.stella)

__artifacts_v2__ = {
    "meta_ai": {
        "name": "Meta AI (Ray-Ban)",
        "description": "Parser for Meta AI companion app artifacts (local + cloud)",
        "author": "Shishir Panta",
        "version": "1.0.0",
        "date": "2026-04-12",
        "requirements": "none",
        "category": "Meta AI",
        "paths": (
            # LOCAL DEVICE ARTIFACTS
            "*/databases/StellaDatabase*",
            "*/app_light_prefs/com.facebook.stella/*",
            
            # CLOUD EXPORT ARTIFACTS
            "*/meta_ai_profile/*.html",
            "*/meta_ai_app/*.html",
            "*/facebook_view/media/*",
        ),
        "function": "get_meta_ai"
    }
}

import json
import os
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
import re

from scripts.artifact_report import ArtifactHtmlReport
from scripts.ilapfuncs import logfunc, open_sqlite_db_readonly


def _ms_to_utc(timestamp_ms):
    """Safely converts millisecond timestamp to UTC string."""
    if not timestamp_ms:
        return ''
    try:
        return datetime.utcfromtimestamp(int(timestamp_ms) / 1000.0).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, OSError):
        return 'Invalid timestamp: ' + str(timestamp_ms)


def _read_xml_key_value(file_path):
    """Safely reads key-value pairs from an XML file."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        return {child.attrib.get('name', 'unknown'): child.text for child in root}
    except (ET.ParseError, FileNotFoundError, KeyError) as e:
        logfunc("[Meta AI] Could not parse XML file " + os.path.basename(file_path) + ": " + str(e))
        return {}


def _parse_binary_prefs(file_path):
    """Parses binary SharedPreferences files (non-XML format)."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        # Decode as UTF-8, ignoring errors
        text = content.decode('utf-8', errors='ignore')
        
        # Clean up the text - remove null bytes and extra whitespace
        text = text.replace('\x00', ' ').replace('\r', ' ').replace('\n', ' ')
        # Normalize multiple spaces to single space
        text = ' '.join(text.split())
        
        # Simple extraction using string splitting
        data = {}
        
        # Define target keys and their expected next keys (to know where value ends)
        extractions = [
            ('device_serial', ['device_frame_color_name', 'soc_build']),
            ('device_uuid', ['cloud_ota_error', 'build_flags_key']),
            ('btc_address', ['device_frame_type', 'device_identifier']),
            ('device_identifier', ['device_lens_color_name', 'feature_key']),
            ('device_frame_type_short_name', ['device_lens_color']),
            ('device_frame_color_name', ['soc_build', 'mcu_build', 'build_flavor']),
            ('device_lens_color_name', ['feature_key', 'sku_code']),
            ('mcu_build', ['device_type']),
            ('soc_build', ['build_flavor']),
            ('device_type', ['device_hardware_type']),
            ('device_hardware_type', ['device_uuid']),
        ]
        
        for key, terminators in extractions:
            # Find the key in the text
            key_pos = text.find(key)
            if key_pos == -1:
                continue
            
            # Start searching after the key name
            value_start = key_pos + len(key)
            
            # Find where the value ends (at the next terminator key)
            value_end = len(text)
            for terminator in terminators:
                term_pos = text.find(terminator, value_start)
                if term_pos != -1 and term_pos < value_end:
                    value_end = term_pos
            
            # Extract and clean the value
            value = text[value_start:value_end].strip()
            
            # Remove leading special characters like $
            if value.startswith('$'):
                value = value[1:]
            
            # Remove any trailing garbage
            value = value.split()[0] if len(value.split()) == 1 else ' '.join(value.split()[:4])
            
            if value and len(value) > 0:
                data[key] = value
        
        return data
        
    except Exception as e:
        logfunc("[Meta AI] Could not parse binary prefs file " + os.path.basename(file_path) + ": " + str(e))
        return {}


def _get_table_columns(cursor, table_name):
    """Get list of columns for a table."""
    cursor.execute("PRAGMA table_info(" + table_name + ")")
    return [col[1] for col in cursor.fetchall()]


def _parse_stella_db(db_path, report_folder):
    """Parses StellaDatabase with streamlined reports."""
    
    try:
        db = open_sqlite_db_readonly(db_path)
        cursor = db.cursor()
        
        # === 1. USER PROFILE ===
        try:
            query = '''SELECT
                user_id as "User ID",
                user_name as "Display Name",
                CASE
                    WHEN length(profile_picture_uri) > 80 
                    THEN '<a href="' || profile_picture_uri || '" target="_blank">' || substr(profile_picture_uri, 1, 80) || '...</a>'
                    ELSE '<a href="' || profile_picture_uri || '" target="_blank">' || profile_picture_uri || '</a>'
                END as "Profile Picture URI",
                datetime(fetch_timestamp_ms/1000, "unixepoch") as "Profile Fetched (UTC)",
                CASE 
                    WHEN eligible_for_c50 = 1 THEN 'Yes' 
                    ELSE 'No' 
                END as "Meta AI Eligible"
            FROM user_profile'''
            
            cursor.execute(query)
            all_rows = cursor.fetchall()
            if all_rows:
                report = ArtifactHtmlReport('Meta AI - User Profile')
                report.start_artifact_report(report_folder, 'User Profile', '')
                report.add_script()
                data_headers = [x[0] for x in cursor.description]
                # Disable HTML escaping for Profile Picture URI column to allow clickable links
                report.write_artifact_data_table(data_headers, all_rows, os.path.basename(db_path), True, True, True, True, True, '', 'dtBasicExample', [2])
                report.end_artifact_report()
                logfunc("[Meta AI] Created 'User Profile' report with " + str(len(all_rows)) + " entries.")
        except sqlite3.OperationalError as e:
            logfunc("[Meta AI] User Profile query failed: " + str(e))
        
        # === 2. PAIRED DEVICES (FROM DB) ===
        try:
            query = '''SELECT
                pairing_id as "Pairing ID (MAC)",
                device_serial as "Serial Number",
                datetime(first_capture_timestamp_ms/1000, "unixepoch") as "First Capture",
                datetime(last_capture_timestamp_ms/1000, "unixepoch") as "Last Capture"
            FROM (
                SELECT 
                    pairing_id,
                    device_serial,
                    MIN(capture_timestamp_ms) as first_capture_timestamp_ms,
                    MAX(capture_timestamp_ms) as last_capture_timestamp_ms
                FROM capture
                WHERE pairing_id != ''
                GROUP BY pairing_id, device_serial
            )
            ORDER BY last_capture_timestamp_ms DESC'''
            
            cursor.execute(query)
            all_rows = cursor.fetchall()
            if all_rows:
                report = ArtifactHtmlReport('Meta AI - Paired Devices (from DB)')
                report.start_artifact_report(report_folder, 'Paired Devices (from DB)', '')
                report.add_script()
                data_headers = [x[0] for x in cursor.description]
                report.write_artifact_data_table(data_headers, all_rows, os.path.basename(db_path), True)
                report.end_artifact_report()
                logfunc("[Meta AI] Created 'Paired Devices (from DB)' report with " + str(len(all_rows)) + " entries.")
        except sqlite3.OperationalError as e:
            logfunc("[Meta AI] Paired Devices query failed: " + str(e))
        
        # === 3. MEDIA TIMELINE (CONSOLIDATED) ===
        try:
            query = '''SELECT
                datetime(cap.capture_timestamp_ms / 1000, "unixepoch") as "Timestamp (Captured UTC)",
                cap.device_serial as "Device Serial",
                cap.pairing_id as "Pairing ID (MAC)",
                up.user_name as "Username",
                cap.type as "Media Type",
                CASE
                    WHEN loc.latitude IS NOT NULL THEN (CAST(loc.latitude AS TEXT) || ', ' || CAST(loc.longitude AS TEXT))
                    ELSE ''
                END as "GPS Coordinates",
                datetime(mi.import_completed_timestamp_ms / 1000, "unixepoch") as "Imported to Phone (UTC)",
                mf.uri as "File Path"
            FROM
                capture AS cap
            LEFT JOIN
                media_item AS mi ON cap.capture_id = mi.capture_id
            LEFT JOIN
                media_item_display AS mid ON mi.media_item_id = mid.media_item_id AND mid.is_current_version = 1
            LEFT JOIN
                media_file AS mf ON mid.display_full_media_file_id = mf.media_file_id
            LEFT JOIN
                media_item_location AS loc ON mi.media_item_id = loc.media_item_id
            LEFT JOIN
                multimodal_metadata AS mm ON mi.media_item_id = mm.media_item_id
            CROSS JOIN
                user_profile AS up
            WHERE
                mf.uri IS NOT NULL
            ORDER BY
                cap.capture_timestamp_ms DESC'''
            
            cursor.execute(query)
            all_rows = cursor.fetchall()
            if all_rows:
                report = ArtifactHtmlReport('Meta AI - Media Timeline')
                report.start_artifact_report(report_folder, 'Media Timeline', '')
                report.add_script()
                data_headers = [x[0] for x in cursor.description]
                report.write_artifact_data_table(data_headers, all_rows, os.path.basename(db_path), True)
                report.end_artifact_report()
                logfunc("[Meta AI] Created 'Media Timeline' report with " + str(len(all_rows)) + " entries.")
            else:
                logfunc("[Meta AI] No media timeline entries found.")
        except sqlite3.OperationalError as e:
            logfunc("[Meta AI] Media Timeline query failed: " + str(e))
        
        db.close()
    except Exception as e:
        logfunc("[Meta AI] StellaDatabase error: " + str(e))


def _parse_device_info(files, report_folder):
    """Extracts device pairing info and linked Meta accounts."""
    paired_devices = {}
    meta_accounts = []

    for file_path in files:
        file_name = os.path.basename(file_path)
        
        # Device metadata from XML
        if file_name == 'connectivity_metadata.xml':
            data = _read_xml_key_value(file_path)
            mac = data.get('DEVICE-METADATA-ID', 'Unknown')
            if mac not in paired_devices:
                paired_devices[mac] = {}
            paired_devices[mac]['mac'] = mac
            paired_devices[mac]['serial'] = data.get('serialNumber', '')
            
        # System info from BINARY preferences file (NOT XML)
        elif file_name.startswith('device_system_info_'):
            # Extract MAC from filename
            mac = file_name.replace('device_system_info_', '')
            if mac not in paired_devices:
                paired_devices[mac] = {}
            
            # Parse binary preferences
            data = _parse_binary_prefs(file_path)
            
            if data:
                paired_devices[mac]['mac'] = data.get('device_identifier', mac)
                paired_devices[mac]['btc'] = data.get('btc_address', '')
                paired_devices[mac]['serial'] = data.get('device_serial', '')
                paired_devices[mac]['uuid'] = data.get('device_uuid', '')
                paired_devices[mac]['frame'] = data.get('device_frame_type_short_name', '')
                paired_devices[mac]['frame_color'] = data.get('device_frame_color_name', '')
                paired_devices[mac]['lens'] = data.get('device_lens_color_name', '')
                paired_devices[mac]['mcu_build'] = data.get('mcu_build', '')
                paired_devices[mac]['soc_build'] = data.get('soc_build', '')

        # Meta account linking - Handle both JSON and plain text formats
        elif file_name == 'meta_fx_cache':
            try:
                # Try JSON first with UTF-8
                with open(file_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    
                for account in cache_data.get('accounts', []):
                    platform = account.get('platform', 'Unknown')
                    username = account.get('username', account.get('email', ''))
                    account_id = account.get('account_id', '')
                    meta_accounts.append((platform, username, account_id))
                    
            except (json.JSONDecodeError, UnicodeDecodeError):
                # If JSON or UTF-8 fails, try with different encoding and regex extraction
                try:
                    # Try reading with latin-1 encoding which accepts all byte values
                    with open(file_path, 'r', encoding='latin-1', errors='ignore') as f:
                        content = f.read()
                    
                    # Extract account IDs
                    account_ids = re.findall(r'"account_id"\s*:\s*"?(\d+)"?', content)
                    platforms = re.findall(r'"account_type"\s*:\s*"([^"]+)"', content)
                    usernames = re.findall(r'"(?:username|email)"\s*:\s*"([^"]+)"', content)
                    
                    for i, account_id in enumerate(account_ids):
                        platform = platforms[i] if i < len(platforms) else 'Unknown'
                        username = usernames[i] if i < len(usernames) else 'N/A'
                        meta_accounts.append((platform, username, account_id))
                    
                    if meta_accounts:
                        logfunc("[Meta AI] Parsed meta_fx_cache using fallback encoding.")
                        
                except Exception as e:
                    logfunc("[Meta AI] Could not parse meta_fx_cache: " + str(e))

    # === 4. PAIRED DEVICES (DETAILED) ===
    if paired_devices:
        device_rows = []
        for mac, info in paired_devices.items():
            device_rows.append((
                info.get('mac', mac),
                info.get('btc', ''),
                info.get('serial', ''),
                info.get('uuid', ''),
                (info.get('frame', '') + ' - ' + info.get('frame_color', '')).strip(' -'),
                info.get('lens', ''),
                info.get('mcu_build', ''),
                info.get('soc_build', '')
            ))
        
        report = ArtifactHtmlReport('Meta AI - Paired Devices (Detailed)')
        report.start_artifact_report(report_folder, 'Paired Devices (Detailed)', '')
        report.add_script()
        data_headers = ('Device ID (MAC)', 'Bluetooth Address', 'Serial Number', 'Device UUID', 'Frame & Color', 'Lens Type', 'MCU Build', 'SoC Build')
        report.write_artifact_data_table(data_headers, device_rows, 'app_light_prefs', True, True, False)  # Changed html_escape to False
        report.end_artifact_report()
        logfunc("[Meta AI] Created 'Paired Devices (Detailed)' report with " + str(len(device_rows)) + " entries.")

    # === 5. LINKED ACCOUNTS ===
    if meta_accounts:
        report = ArtifactHtmlReport('Meta AI - Linked Accounts')
        report.start_artifact_report(report_folder, 'Linked Accounts', '')
        report.add_script()
        data_headers = ('Platform', 'Username / Email', 'Account ID')
        report.write_artifact_data_table(data_headers, meta_accounts, 'meta_fx_cache', True)
        report.end_artifact_report()
        logfunc("[Meta AI] Created 'Linked Accounts' report with " + str(len(meta_accounts)) + " entries.")


def _parse_cloud_conversations(files, report_folder):
    """Parses AI conversation history from cloud HTML exports."""
    import re
    from html import unescape
    
    conversations = []
    
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            # Extract conversation date from filename pattern
            conv_dates = re.findall(r'Conversation with Meta AI_(\d{2}-\d{2}-\d{4})_\d+\.txt', html_content)
            
            # Extract conversation text blocks
            conv_blocks = re.findall(r'<td class="_2piu _a6_r">(Conversation with Meta AI.*?)</td>', html_content, re.DOTALL)
            
            for i, block in enumerate(conv_blocks):
                # Clean HTML entities
                block = unescape(block)
                
                # Extract individual messages
                messages = re.findall(r'(You|Meta AI): (.+?)(?=(?:You|Meta AI):|$)', block, re.DOTALL)
                
                conv_date = conv_dates[i] if i < len(conv_dates) else 'Unknown'
                
                for speaker, message in messages:
                    message_clean = message.strip().replace('\n', ' ')
                    if message_clean and message_clean != 'Conversation with Meta AI':
                        conversations.append((conv_date, speaker, message_clean))
                        
        except Exception as e:
            logfunc("[Meta AI] Could not parse cloud conversations: " + str(e))
    
    # Create report
    if conversations:
        report = ArtifactHtmlReport('Meta AI - AI Conversations (Cloud)')
        report.start_artifact_report(report_folder, 'AI Conversations (Cloud)', '')
        report.add_script()
        data_headers = ('Date', 'Speaker', 'Message')
        report.write_artifact_data_table(data_headers, conversations, 'your_ai_conversations.html', True)
        report.end_artifact_report()
        logfunc("[Meta AI] Created 'AI Conversations (Cloud)' report with " + str(len(conversations)) + " messages.")
    else:
        logfunc("[Meta AI] No cloud conversation data found.")


def _parse_cloud_devices(files, report_folder):
    """Parses connected device history from cloud HTML exports."""
    import re
    
    devices = []
    
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            # Extract serial number
            serial_match = re.search(r'<td class="_a6_q">Serial number</td>\s*<td class="_2piu _a6_r">([^<]+)</td>', html_content)
            serial = serial_match.group(1) if serial_match else 'Unknown'
            
            # Extract update time
            time_match = re.search(r'<td class="_a6_q">Update time</td>\s*<td class="_2piu _a6_r">([^<]+)</td>', html_content)
            update_time = time_match.group(1) if time_match else ''
            
            if serial != 'Unknown':
                devices.append((serial, update_time))
                
        except Exception as e:
            logfunc("[Meta AI] Could not parse cloud devices: " + str(e))
    
    # Create report
    if devices:
        report = ArtifactHtmlReport('Meta AI - Connected Devices (Cloud)')
        report.start_artifact_report(report_folder, 'Connected Devices (Cloud)', '')
        report.add_script()
        data_headers = ('Serial Number', 'Last Update')
        report.write_artifact_data_table(data_headers, devices, 'connected_devices.html', True)
        report.end_artifact_report()
        logfunc("[Meta AI] Created 'Connected Devices (Cloud)' report with " + str(len(devices)) + " entries.")
    else:
        logfunc("[Meta AI] No cloud device data found.")


def _parse_cloud_media(files, report_folder):
    """Parses media library from cloud HTML exports."""
    import re
    
    media_items = []
    
    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                html_content = f.read()
            
            # Extract all media entries (multiple <section> blocks)
            sections = re.findall(r'<section class="_3-95 _a6-g">.*?</section>', html_content, re.DOTALL)
            
            for section in sections:
                # Extract device ID
                device_match = re.search(r'<td class="_a6_q">Device ID</td>\s*<td class="_2piu _a6_r">([^<]+)</td>', section)
                device_id = device_match.group(1) if device_match else 'Unknown'
                
                # Extract media file path
                media_match = re.search(r'href="(posts/media/your_posts/[^"]+)"', section)
                media_path = media_match.group(1) if media_match else ''
                
                # Extract timestamp (appears in empty <td> after media)
                time_match = re.search(r'<td class="_2piu _a6_r">([A-Z][a-z]{2} \d{2}, \d{4} \d{1,2}:\d{2} [ap]m)</td>', section)
                timestamp = time_match.group(1) if time_match else ''
                
                if media_path:
                    media_items.append((device_id, timestamp, media_path))
                    
        except Exception as e:
            logfunc("[Meta AI] Could not parse cloud media: " + str(e))
    
    # Create report
    if media_items:
        report = ArtifactHtmlReport('Meta AI - Cloud Media Library')
        report.start_artifact_report(report_folder, 'Cloud Media Library', '')
        report.add_script()
        data_headers = ('Device ID', 'Timestamp', 'Media File Path')
        report.write_artifact_data_table(data_headers, media_items, 'meta_ai_media.html', True)
        report.end_artifact_report()
        logfunc("[Meta AI] Created 'Cloud Media Library' report with " + str(len(media_items)) + " entries.")
    else:
        logfunc("[Meta AI] No cloud media data found.")


def get_meta_ai(files_found, report_folder, seeker, wrap_text):
    """Main entry point - orchestrates all parsers."""
    logfunc("\n[Meta AI] === Starting Meta AI Parsing ===")
    
    # === CATEGORIZE FILES ===
    # Local device files
    stella_dbs = [f for f in files_found if "StellaDatabase" in f and not f.endswith(('-wal', '-shm', '-journal'))]
    light_prefs = [f for f in files_found if 'app_light_prefs' in f]
    
    # Cloud export files
    cloud_conversations = [f for f in files_found if 'your_ai_conversations.html' in f]
    cloud_devices = [f for f in files_found if 'connected_devices.html' in f]
    cloud_media = [f for f in files_found if 'meta_ai_media.html' in f]
    
    # === PROCESS LOCAL ARTIFACTS (Reports 1-5) ===
    if stella_dbs:
        _parse_stella_db(stella_dbs[0], report_folder)
    else:
        logfunc("[Meta AI] StellaDatabase not found.")

    if light_prefs:
        _parse_device_info(light_prefs, report_folder)
    
    # === PROCESS CLOUD ARTIFACTS (Reports 6-8) ===
    if cloud_conversations:
        _parse_cloud_conversations(cloud_conversations, report_folder)
    
    if cloud_devices:
        _parse_cloud_devices(cloud_devices, report_folder)
    
    if cloud_media:
        _parse_cloud_media(cloud_media, report_folder)
    
    logfunc("[Meta AI] === Meta AI Parsing Complete ===")