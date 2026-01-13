import logging
import pandas as pd
from sqlalchemy import create_engine, Table, MetaData
from sqlalchemy.dialects.postgresql import insert
from config.settings import DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME

logger = logging.getLogger(__name__)

def get_engine():
    """Create SQLAlchemy engine."""
    from config.settings import DATABASE_URL
    if DATABASE_URL:
        return create_engine(DATABASE_URL)
    conn_str: str = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return create_engine(conn_str)

def save_to_db(df: pd.DataFrame) -> bool:
    """
    Load data into PostgreSQL database using Upsert (ON CONFLICT).
    """
    if df.empty:
        logger.info("Empty DataFrame, skipping database load.")
        return False

    try:
        engine = get_engine()
        metadata = MetaData()
        # Reflect the fact_price table
        fact_price = Table('fact_price', metadata, autoload_with=engine)

        # Convert DataFrame to list of dictionaries for insertion
        records = df.to_dict(orient='records')

        with engine.begin() as conn:
            for record in records:
                # Create the insert statement
                stmt = insert(fact_price).values(record)
                
                # Create the upsert logic: ON CONFLICT (stock_id, date) DO UPDATE
                upsert_stmt = stmt.on_conflict_do_update(
                    index_elements=['stock_id', 'date'],
                    set_={
                        'open_price': stmt.excluded.open_price,
                        'high_price': stmt.excluded.high_price,
                        'low_price': stmt.excluded.low_price,
                        'close_price': stmt.excluded.close_price,
                        'volume': stmt.excluded.volume,
                        'adj_close': stmt.excluded.adj_close,
                        'ma5': stmt.excluded.ma5,
                        'ma20': stmt.excluded.ma20
                    }
                )
                conn.execute(upsert_stmt)
        
        logger.info(f"Successfully loaded {len(df)} records to database.")
        return True
    except Exception as e:
        logger.error(f"Error loading data to database: {str(e)}")
        return False
