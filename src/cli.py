"""Command-line interface for Satellite Tile Manager."""

import argparse
import sys


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Satellite Tile Manager - Manage satellite map tiles for ML training"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Server command
    server_parser = subparsers.add_parser("serve", help="Start the API server")
    server_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    server_parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    server_parser.add_argument("--reload", action="store_true", help="Enable auto-reload")

    # Download command
    download_parser = subparsers.add_parser("download", help="Download tiles for a region")
    download_parser.add_argument("--name", required=True, help="Region name")
    download_parser.add_argument("--min-lat", type=float, required=True)
    download_parser.add_argument("--max-lat", type=float, required=True)
    download_parser.add_argument("--min-lon", type=float, required=True)
    download_parser.add_argument("--max-lon", type=float, required=True)
    download_parser.add_argument("--zoom", type=int, default=16, help="Zoom level")
    download_parser.add_argument(
        "--provider",
        nargs="+",
        default=["naip"],
        help="Providers to download from",
    )

    # Export command
    export_parser = subparsers.add_parser("export", help="Export tiles")
    export_parser.add_argument("--region-id", type=int, help="Region ID to export")
    export_parser.add_argument(
        "--format",
        choices=["manifest", "zip", "drone"],
        default="manifest",
    )
    export_parser.add_argument("--output", "-o", help="Output file path")

    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize database")

    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn
        from src.db import init_db

        init_db()
        uvicorn.run(
            "src.api.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )

    elif args.command == "download":
        import asyncio
        from src.db import init_db
        from src.db.base import SyncSessionLocal
        from src.db.models import ProviderName, Region
        from src.services.tile_manager import TileManager

        init_db()
        db = SyncSessionLocal()

        # Create region
        region = Region(
            name=args.name,
            min_lat=args.min_lat,
            max_lat=args.max_lat,
            min_lon=args.min_lon,
            max_lon=args.max_lon,
            target_zoom=args.zoom,
        )
        db.add(region)
        db.commit()
        db.refresh(region)

        print(f"Created region: {region.name} (ID: {region.id})")

        # Download tiles
        manager = TileManager(db)
        providers = [ProviderName(p) for p in args.provider]

        print(f"Downloading tiles from: {', '.join(args.provider)}")
        asyncio.run(manager.download_region(region.id, providers, args.zoom))

        db.refresh(region)
        print(f"Downloaded {region.downloaded_tiles}/{region.total_tiles} tiles")

        db.close()

    elif args.command == "export":
        import json
        from src.db import init_db
        from src.db.base import SyncSessionLocal
        from src.db.models import Region, Tile, TileStatus

        init_db()
        db = SyncSessionLocal()

        if not args.region_id:
            print("Error: --region-id required for export")
            sys.exit(1)

        tiles = (
            db.query(Tile)
            .filter(Tile.region_id == args.region_id, Tile.status == TileStatus.READY)
            .all()
        )

        manifest = {
            "version": "1.0",
            "tile_count": len(tiles),
            "tiles": [
                {
                    "id": t.id,
                    "file_path": t.file_path,
                    "tile_x": t.tile_x,
                    "tile_y": t.tile_y,
                    "zoom": t.zoom,
                    "gsd": t.gsd,
                    "bounds": {
                        "min_lat": t.min_lat,
                        "max_lat": t.max_lat,
                        "min_lon": t.min_lon,
                        "max_lon": t.max_lon,
                    },
                }
                for t in tiles
            ],
        }

        output = args.output or f"region_{args.region_id}_manifest.json"
        with open(output, "w") as f:
            json.dump(manifest, f, indent=2)

        print(f"Exported {len(tiles)} tiles to {output}")
        db.close()

    elif args.command == "init":
        from src.db import init_db

        init_db()
        print("Database initialized")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
