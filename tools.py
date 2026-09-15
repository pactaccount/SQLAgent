import re
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

def get_schema_json(db_uri: str) -> dict:
    """
    Returns a structured dictionary of all tables and their columns.
    Format: {"tables": [{"name": "table1", "columns": [{"name": "c1", "type": "int"}]}]}
    """
    try:
        engine = create_engine(db_uri)
        inspector = inspect(engine)
        
        tables = []
        for table_name in inspector.get_table_names():
            columns = []
            for col in inspector.get_columns(table_name):
                columns.append({
                    "name": col["name"],
                    "type": str(col["type"])
                })
            tables.append({
                "name": table_name,
                "columns": columns
            })
            
        return {"success": True, "tables": tables}
    except Exception as e:
        return {"success": False, "error": str(e)}

def execute_sql(sql: str, db_uri: str, bypass_approval: bool = False) -> dict:
    """
    Executes a SQL query against the database specified by db_uri.
    Intercepts destructive queries for Human-in-the-Loop approval unless bypassed.
    """
    sql_upper = sql.upper().strip()
    
    # 1. HITL Interception
    destructive_keywords = ["DROP", "UPDATE", "DELETE", "INSERT", "ALTER", "CREATE", "GRANT", "REVOKE"]
    is_destructive = any(re.search(rf'\b{word}\b', sql_upper) for word in destructive_keywords)
    
    if is_destructive and not bypass_approval:
        return {
            "success": True,
            "requires_approval": True,
            "result": None,
            "message": "Query flagged for Human-in-the-Loop approval."
        }
        
    # 2. Execute the query
    import decimal
    try:
        engine = create_engine(db_uri)
        with engine.connect() as connection:
            # We use an explicit transaction block for destructive queries
            trans = connection.begin()
            try:
                result = connection.execute(text(sql))
                
                # If it's a SELECT returning rows
                if result.returns_rows:
                    result_data = []
                    for row in result:
                        row_dict = {}
                        for k, v in row._mapping.items():
                            if isinstance(v, decimal.Decimal):
                                row_dict[k] = float(v)
                            else:
                                row_dict[k] = v
                        result_data.append(row_dict)
                    trans.commit()
                    return {"success": True, "requires_approval": False, "result": result_data}
                else:
                    # For INSERT/UPDATE/DELETE
                    trans.commit()
                    return {"success": True, "requires_approval": False, "result": [{"status": "Success", "rows_affected": result.rowcount}]}
            except Exception as e:
                trans.rollback()
                raise e
                
    except SQLAlchemyError as e:
        return {
            "success": False,
            "error": f"Database Error: {str(e)}"
        }
    except Exception as e:
         return {
            "success": False,
            "error": f"Unexpected Error: {str(e)}"
        }

def get_schema_for_query(query: str, tenant_id: str):
    """
    Uses the Vector Store to find the most relevant schema tables for a specific tenant.
    """
    from vector_store import vector_store
    
    # Get top 5 tables for this specific tenant
    relevant_schema_docs = vector_store.search_schema(query, tenant_id, k=5)
    
    if not relevant_schema_docs:
         return "No schema available. Ensure the database connection is set up and initialized."
         
    return "\n\n".join(relevant_schema_docs)
