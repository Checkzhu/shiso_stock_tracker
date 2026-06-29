# -*- coding: utf-8 -*-
"""数据库迁移脚本 - 添加邀请码相关表和字段"""
from __future__ import print_function
import sqlite3
import sys
import os

DB_PATH = r"/opt/shiso_stock_tracker/data/stock_tracker.db"


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"正在迁移数据库: {DB_PATH}")

    # 1. 创建 invite_codes 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invite_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(20) UNIQUE NOT NULL,
            role VARCHAR(20) DEFAULT 'viewer',
            max_uses INTEGER DEFAULT 0,
            used_count INTEGER DEFAULT 0,
            created_by INTEGER,
            expires_at DATETIME,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            note VARCHAR(200)
        )
    """)
    print("✓ invite_codes 表已创建")

    # 2. 为 users 表添加 invite_code_id 列
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'invite_code_id' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN invite_code_id INTEGER REFERENCES invite_codes(id)")
        print("✓ users.invite_code_id 列已添加")
    else:
        print("- users.invite_code_id 列已存在，跳过")

    # 3. 为 ai_providers 表添加列（如果不存在）
    cursor.execute("PRAGMA table_info(ai_providers)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'name' not in columns:
        cursor.execute("ALTER TABLE ai_providers ADD COLUMN name VARCHAR(100)")
        print("✓ ai_providers.name 列已添加")
    else:
        print("- ai_providers.name 列已存在，跳过")

    # 4. 创建 analysis_tasks 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_type VARCHAR(20) DEFAULT 'batch',
            status VARCHAR(20) DEFAULT 'pending',
            provider_id INTEGER REFERENCES ai_providers(id),
            total_stocks INTEGER DEFAULT 0,
            completed_stocks INTEGER DEFAULT 0,
            failed_stocks INTEGER DEFAULT 0,
            current_stock VARCHAR(100),
            error_message TEXT,
            triggered_by VARCHAR(50),
            started_at DATETIME,
            completed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✓ analysis_tasks 表已创建")

    # 5. 创建 stock_analyses 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_id INTEGER NOT NULL REFERENCES tracked_stocks(id),
            task_id INTEGER REFERENCES analysis_tasks(id),
            provider_id INTEGER REFERENCES ai_providers(id),
            model_name VARCHAR(100),
            version INTEGER DEFAULT 1,
            is_current INTEGER DEFAULT 1,
            buy_price_range VARCHAR(100),
            buy_strategy TEXT,
            target_price VARCHAR(100),
            stop_loss_price VARCHAR(50),
            target_desc TEXT,
            holding_period VARCHAR(50),
            expected_return VARCHAR(50),
            rise_reasons TEXT,
            industry_tech TEXT,
            physics_limits TEXT,
            substitution_threat TEXT,
            supply_demand_bias TEXT,
            geopolitical_risk TEXT,
            capacity_feasibility TEXT,
            demand_sustainability TEXT,
            valuation_rationality TEXT,
            risks TEXT,
            score REAL,
            score_comment VARCHAR(500),
            summary TEXT,
            raw_response TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✓ stock_analyses 表已创建")

    # 6. 为 tracked_stocks 添加 serenity_scores 列
    cursor.execute("PRAGMA table_info(tracked_stocks)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'serenity_scores' not in columns:
        cursor.execute("ALTER TABLE tracked_stocks ADD COLUMN serenity_scores TEXT")
        print("✓ tracked_stocks.serenity_scores 列已添加")
    else:
        print("- tracked_stocks.serenity_scores 列已存在，跳过")

    # 7. 为 tracked_stocks 添加 depth_analysis 列
    if 'depth_analysis' not in columns:
        cursor.execute("ALTER TABLE tracked_stocks ADD COLUMN depth_analysis TEXT")
        print("✓ tracked_stocks.depth_analysis 列已添加")
    else:
        print("- tracked_stocks.depth_analysis 列已存在，跳过")

    # 8. 为 stock_analyses 添加 serenity_scores 列
    cursor.execute("PRAGMA table_info(stock_analyses)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'serenity_scores' not in columns:
        cursor.execute("ALTER TABLE stock_analyses ADD COLUMN serenity_scores TEXT")
        print("✓ stock_analyses.serenity_scores 列已添加")
    else:
        print("- stock_analyses.serenity_scores 列已存在，跳过")

    # 9. 为 stock_analyses 添加 depth_analysis 列
    if 'depth_analysis' not in columns:
        cursor.execute("ALTER TABLE stock_analyses ADD COLUMN depth_analysis TEXT")
        print("✓ stock_analyses.depth_analysis 列已添加")
    else:
        print("- stock_analyses.depth_analysis 列已存在，跳过")

    # 10. 为 stock_analyses 添加 feasibility_assessment 列
    if 'feasibility_assessment' not in columns:
        cursor.execute("ALTER TABLE stock_analyses ADD COLUMN feasibility_assessment TEXT")
        print("✓ stock_analyses.feasibility_assessment 列已添加")
    else:
        print("- stock_analyses.feasibility_assessment 列已存在，跳过")

    # 11. 为 stock_analyses 添加 irreplaceability 列
    if 'irreplaceability' not in columns:
        cursor.execute("ALTER TABLE stock_analyses ADD COLUMN irreplaceability TEXT")
        print("✓ stock_analyses.irreplaceability 列已添加")
    else:
        print("- stock_analyses.irreplaceability 列已存在，跳过")

    # 12. 为 stock_analyses 添加 chain_flow 列
    if 'chain_flow' not in columns:
        cursor.execute("ALTER TABLE stock_analyses ADD COLUMN chain_flow TEXT")
        print("✓ stock_analyses.chain_flow 列已添加")
    else:
        print("- stock_analyses.chain_flow 列已存在，跳过")

    # 13. 为 tracked_stocks 添加行情缓存列
    cursor.execute("PRAGMA table_info(tracked_stocks)")
    columns = [row[1] for row in cursor.fetchall()]
    cache_columns = {
        'last_current_price': 'REAL',
        'last_change_pct': 'REAL',
        'return_1w': 'REAL',
        'return_1m': 'REAL',
        'return_3m': 'REAL',
        'return_1y': 'REAL',
        'last_quote_time': 'DATETIME',
        'last_quote_date': 'VARCHAR(10)',
    }
    for col_name, col_type in cache_columns.items():
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE tracked_stocks ADD COLUMN {col_name} {col_type}")
            print(f"✓ tracked_stocks.{col_name} 列已添加")
        else:
            print(f"- tracked_stocks.{col_name} 列已存在，跳过")

    conn.commit()
    conn.close()
    print("\n迁移完成！可以启动服务器了。")


if __name__ == '__main__':
    migrate()