"""Read operational integrity and prepaid-work status; no workers are started."""
import argparse
import json

from hponas.operations import database_inventory, ledger_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--ledger', required=True)
    args = parser.parse_args()
    try:
        result = {'database': database_inventory(args.database), 'ledger': ledger_status(args.ledger)}
        result['status'] = result['ledger']['status']
    except Exception as exc:
        result = {'status': 'error', 'error_type': type(exc).__name__, 'message': str(exc)}
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
