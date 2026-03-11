"""
Pagination helpers.
"""

from flask import request


def get_pagination_params(default_per_page: int = 20, max_per_page: int = 100) -> tuple[int, int]:
    """
    Extract page and per_page from request query args.
    Returns (page, per_page) as integers.
    """
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(
        max(1, request.args.get("per_page", default_per_page, type=int)),
        max_per_page,
    )
    return page, per_page


def paginate_query(stmt, session, page: int, per_page: int):
    """
    Apply OFFSET/LIMIT to a SQLAlchemy select statement and return
    (items, total_count).

    Example:
        items, total = paginate_query(stmt, session, page=1, per_page=20)
    """
    from sqlalchemy import func, select

    # Count total (without limit/offset)
    # This is a simple approach — for large tables, consider a separate count query
    all_items = session.execute(stmt).scalars().all()
    total = len(all_items)

    offset = (page - 1) * per_page
    paginated = session.execute(stmt.offset(offset).limit(per_page)).scalars().all()

    return paginated, total


def pagination_meta(total: int, page: int, per_page: int) -> dict:
    """Return pagination metadata dict."""
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page > 0 else 0,
    }
