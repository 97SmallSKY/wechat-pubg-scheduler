"""Execute one workspace SQL request in a short-lived PostgreSQL client process."""

import json
import os
import resource
import sys

MAX_ROWS = 1000
MAX_RESULT = 1024 * 1024


def execute(request):
    import psycopg2

    try:
        connection = psycopg2.connect(os.environ["RELAY_WORKSPACE_DSN"], connect_timeout=3)
    except psycopg2.OperationalError:
        return 503, {"error": "开发数据库暂时不可用"}

    try:
        with connection, connection.cursor() as cursor:
            cursor.execute(request["sql"], request.get("params"))
            columns = [field.name for field in cursor.description] if cursor.description else []
            rows = cursor.fetchmany(MAX_ROWS + 1) if columns else []
            result = {"command": cursor.statusmessage, "row_count": cursor.rowcount,
                      "columns": columns, "rows": rows[:MAX_ROWS], "truncated": len(rows) > MAX_ROWS}
            response = json.dumps([200, result], ensure_ascii=False, default=str, allow_nan=False)
            if len(response.encode("utf-8")) > MAX_RESULT:
                raise ValueError("查询结果超过 1 MiB，请减少返回列或使用 LIMIT")
        return response
    except psycopg2.Error as error:
        if error.pgcode == "57014":
            return 408, {"error": "开发数据库查询超时"}
        return 400, {"error": error.diag.message_primary or "SQL 请求无效", "sqlstate": error.pgcode}
    finally:
        connection.close()


def main():
    # libpq buffers the result before Python can limit the returned rows.
    limit = 256 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    try:
        result = execute(json.load(sys.stdin))
    except (IndexError, TypeError, ValueError) as error:
        result = 400, {"error": str(error)}
    except MemoryError:
        result = 413, {"error": "查询结果过大，请缩小查询范围"}
    print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
