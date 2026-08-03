"""MMDB 文件管理端点（v1）。

前端 ``threat-intel.ts`` 调用 ``/api/v1/intelligence/mmdb/*``，
这里挂载对应的 v1 路由，代理到 gateway 侧的 MMDBReader 配置目录。

注意：上传/下载 MMDB 文件操作的是 **gateway 共享的数据目录**
（由 ``MMDB_DIR`` 环境变量或 Settings.mmdb_dir 指定），
admin 与 gateway 通过同一挂载卷共享文件。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse

from fangyu_shared.schemas.common import SuccessResponse

from src.interfaces.http.dependencies import get_current_user_id

router = APIRouter(prefix="/intelligence/mmdb", tags=["mmdb"])

# MMDB 文件存储目录：与 gateway 共享，通过挂载卷传递
_MMDB_DIR = Path(os.getenv("MMDB_DIR", "/data/mmdb"))

_FILE_TYPES = {
    "country": "GeoLite2-Country.mmdb",
    "asn": "GeoLite2-ASN.mmdb",
}


def _file_status(file_type: str) -> dict[str, Any]:
    filename = _FILE_TYPES.get(file_type)
    if not filename:
        raise HTTPException(status_code=400, detail=f"未知 file_type: {file_type}")
    path = _MMDB_DIR / filename
    exists = path.exists()
    return {
        "file_type": file_type,
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else None,
        "modified_at": path.stat().st_mtime if exists else None,
    }


@router.get("/status", summary="查询 MMDB 文件状态")
async def mmdb_status(
    _: int = Depends(get_current_user_id),
) -> SuccessResponse[dict]:
    files = [_file_status(ft) for ft in _FILE_TYPES]
    return SuccessResponse(data={
        "storage_dir": str(_MMDB_DIR),
        "files": files,
    })


@router.post("/upload", summary="上传 MMDB 文件", status_code=status.HTTP_200_OK)
async def upload_mmdb(
    file: UploadFile,
    file_type: str = Query(..., pattern="^(country|asn)$"),
    _: int = Depends(get_current_user_id),
) -> SuccessResponse[dict]:
    filename = _FILE_TYPES[file_type]
    _MMDB_DIR.mkdir(parents=True, exist_ok=True)
    dest = _MMDB_DIR / filename
    try:
        content = await file.read()
        dest.write_bytes(content)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"文件写入失败: {exc}") from exc
    return SuccessResponse(data=_file_status(file_type))


@router.delete("/{file_type}", summary="删除 MMDB 文件")
async def delete_mmdb(
    file_type: str,
    _: int = Depends(get_current_user_id),
) -> SuccessResponse[dict]:
    if file_type not in _FILE_TYPES:
        raise HTTPException(status_code=400, detail=f"未知 file_type: {file_type}")
    path = _MMDB_DIR / _FILE_TYPES[file_type]
    if path.exists():
        path.unlink()
    return SuccessResponse(data=_file_status(file_type))


@router.post("/compare-cidrs", summary="批量查询 CIDR 在 MMDB 中的原始归属")
async def compare_cidrs(
    cidrs: list[str],
    _: int = Depends(get_current_user_id),
) -> SuccessResponse[dict]:
    """返回各 CIDR 在 MMDB 中的国家判定，供前端与修正值做覆盖对比。

    取网段的首个可用地址代表整段查询——MMDB 按网段存储，同一 CIDR 内的
    国家判定通常一致，逐 IP 查询没有额外收益。

    一次打开库文件查完所有网段，避免逐条 open_database 的开销。
    MMDB 缺失时不报错，返回空 mapping 让前端把该列显示为「无数据」。
    """
    import ipaddress

    if not cidrs:
        return SuccessResponse(data={"results": {}})
    if len(cidrs) > 200:
        raise HTTPException(status_code=400, detail="单次最多对比 200 个网段")

    country_path = _MMDB_DIR / "GeoLite2-Country.mmdb"
    if not country_path.exists():
        return SuccessResponse(data={"results": {}, "available": False})

    try:
        import maxminddb  # type: ignore[import]
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="maxminddb 库未安装") from exc

    results: dict[str, dict[str, Any]] = {}
    try:
        with maxminddb.open_database(str(country_path)) as reader:
            for cidr in cidrs:
                try:
                    network = ipaddress.ip_network(cidr.strip(), strict=False)
                except ValueError:
                    continue
                try:
                    rec = reader.get(str(network.network_address)) or {}
                except (ValueError, TypeError):
                    continue
                country = (rec.get("country") or {}).get("iso_code")
                results[cidr] = {
                    "country": country,
                    "continent": (rec.get("continent") or {}).get("code"),
                }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"MMDB 查询失败: {exc}") from exc

    return SuccessResponse(data={"results": results, "available": True})


@router.get("/test", summary="测试 IP 的 MMDB 画像")
async def test_mmdb_ip(
    ip: str | None = Query(None),
    _: int = Depends(get_current_user_id),
) -> SuccessResponse[dict]:
    """对指定 IP 做现场 MMDB 查询，便于验证 MMDB 文件是否正确加载。

    直接使用 maxminddb 库，不依赖 gateway-api 的跨服务导入。
    """
    try:
        import maxminddb  # type: ignore[import]
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="maxminddb 库未安装，请在 admin-api 中添加依赖") from exc

    country_path = _MMDB_DIR / "GeoLite2-Country.mmdb"
    asn_path = _MMDB_DIR / "GeoLite2-ASN.mmdb"
    target_ip = (ip or "8.8.8.8").strip()

    country_result: dict = {}
    asn_result: dict = {}
    errors: list[str] = []

    if country_path.exists():
        try:
            with maxminddb.open_database(str(country_path)) as reader:
                country_result = reader.get(target_ip) or {}
        except Exception as exc:
            errors.append(f"country: {exc}")
    else:
        errors.append(f"GeoLite2-Country.mmdb 不存在（路径：{country_path}）")

    if asn_path.exists():
        try:
            with maxminddb.open_database(str(asn_path)) as reader:
                asn_result = reader.get(target_ip) or {}
        except Exception as exc:
            errors.append(f"asn: {exc}")
    else:
        errors.append(f"GeoLite2-ASN.mmdb 不存在（路径：{asn_path}）")

    if not country_result and not asn_result and errors:
        raise HTTPException(status_code=500, detail=f"MMDB 查询失败: {'; '.join(errors)}")

    return SuccessResponse(data={
        "ip": target_ip,
        "country": country_result,
        "asn": asn_result,
        **({"warnings": errors} if errors else {}),
    })
