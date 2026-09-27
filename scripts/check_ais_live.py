#!/usr/bin/env python3
# AISStream Live Connectivity Check CLI

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingestion.ais.aisstream_provider import AISStreamProvider
from src.ingestion.ais.live_buffer import LiveAISBuffer
from src.ingestion.ais.quality import generate_quality_report


def main():
    parser = argparse.ArgumentParser(description='AISStream Live Connectivity Check')
    parser.add_argument('--duration', type=int, default=60, help='Test duration in seconds')
    parser.add_argument('--api-key', default=None, help='AISStream API Key')
    parser.add_argument('--min-lon', type=float, default=-6.0, help='AOI min longitude')
    parser.add_argument('--min-lat', type=float, default=35.8, help='AOI min latitude')
    parser.add_argument('--max-lon', type=float, default=-5.0, help='AOI max longitude')
    parser.add_argument('--max-lat', type=float, default=36.2, help='AOI max latitude')
    args = parser.parse_args()

    api_key = (args.api_key or os.getenv('AISSTREAM_API_KEY', '')).strip()

    print('=' * 50)
    print('AISSTREAM LIVE CONNECTIVITY CHECK')
    print('=' * 50)
    print('Provider:')
    print('AISStream')
    print()

    if not api_key:
        print('Authentication:')
        print('FAILED (NOT_CONFIGURED)')
        print()
        print('Status:')
        print('NOT_CONFIGURED')
        print()
        print('-' * 50)
        print('[!] AISSTREAM_API_KEY is not configured in the environment.')
        print('[!] Set AISSTREAM_API_KEY to a valid key to connect to the live stream.')
        print('=' * 50)
        sys.exit(0)

    buffer = LiveAISBuffer(buffer_hours=48.0)
    bbox = (args.min_lon, args.min_lat, args.max_lon, args.max_lat)

    print(f'Target AOI: [{args.min_lon} deg E, {args.min_lat} deg N to {args.max_lon} deg E, {args.max_lat} deg N]')
    print(f'Monitoring duration: {args.duration} seconds...')
    print('-' * 50)

    provider = AISStreamProvider(
        api_key=api_key,
        bbox=bbox,
        buffer=buffer,
        auto_start=True,
    )

    start_time = time.time()
    try:
        while time.time() - start_time < args.duration:
            time.sleep(1.0)
            if provider.messages_received > 0:
                print(f'[*] Ingested {provider.messages_received} messages ({provider.position_messages} positions, {len(buffer)} in buffer)...', flush=True)
    except KeyboardInterrupt:
        print('Interrupted by operator')
    finally:
        provider.stop()

    print()
    print('-' * 50)
    status = provider.get_status().value

    auth_status = 'SUCCESS' if provider.messages_received > 0 or status == 'CONNECTED' else ('FAILED' if status == 'AUTH_REQUIRED' else 'PENDING')
    sub_status = 'SUCCESS' if provider.messages_received > 0 or status in ['CONNECTED', 'CONNECTING'] else 'FAILED'
    buffer_status = 'SUCCESS' if len(buffer) > 0 else ('SUCCESS' if provider.position_messages == 0 else 'FAILED')

    unique_vessels = len(set(o.mmsi for o in buffer._observations))

    print('Authentication:')
    print(auth_status)
    print()
    print('Subscription:')
    print(sub_status)
    print()
    print('Messages:')
    print(provider.messages_received)
    print()
    print('Position reports:')
    print(provider.position_messages)
    print()
    print('Unique vessels:')
    print(unique_vessels)
    print()
    print('Latest observation:')
    print(provider.last_position_at or 'N/A')
    print()
    print('Buffer insertion:')
    print(buffer_status)
    print()

    final_status = 'CONNECTED' if (provider.messages_received > 0 or status == 'CONNECTED') else ('FAILED' if status in ['AUTH_REQUIRED', 'PROVIDER_ERROR'] else status)
    print('Status:')
    print(final_status)
    print()
    print('=' * 50)

    if len(buffer) > 0:
        report = generate_quality_report(
            observations=buffer._observations,
            provider_name='AISStream',
            output_path='data/results/ais/live_quality_report.json',
        )
        print('[v] Live quality audit saved to data/results/ais/live_quality_report.json')


if __name__ == '__main__':
    main()
