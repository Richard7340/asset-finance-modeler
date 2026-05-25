from __future__ import annotations

from typing import Any

from asset_finance_modeler.store.projects import Project, SQLiteProjectStore, new_project_id


def make_project_create(store: SQLiteProjectStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        project = Project(
            id=new_project_id(),
            tenant_id=args.get("tenant_id", "default"),
            name=args["name"],
            description=args.get("description", ""),
            asset_type=args.get("asset_type"),
            region=args.get("region"),
            tags=args.get("tags", []),
        )
        store.save(project)
        return {"project_id": project.id, "name": project.name}

    return _handle


def make_project_list(store: SQLiteProjectStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        tenant_id = args.get("tenant_id", "default")
        projects = store.list_by_tenant(tenant_id, include_archived=args.get("include_archived", False))
        return {
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "asset_type": p.asset_type,
                    "region": p.region,
                    "scenarios": len(p.scenario_ids),
                    "archived": p.archived,
                }
                for p in projects
            ]
        }

    return _handle


def make_project_get(store: SQLiteProjectStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        project = store.get(args["project_id"])
        if project is None:
            return {"error": f"Project {args['project_id']} not found"}
        return {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "asset_type": project.asset_type,
            "region": project.region,
            "tags": project.tags,
            "scenario_ids": project.scenario_ids,
            "archived": project.archived,
            "metadata": project.metadata,
        }

    return _handle


def make_project_archive(store: SQLiteProjectStore) -> Any:
    def _handle(args: dict[str, Any]) -> dict[str, Any]:
        store.archive(args["project_id"])
        return {"archived": True, "project_id": args["project_id"]}

    return _handle
