import sqlite3
import random
from datetime import datetime, timedelta
import os

def create_b2b_database():
    db_path = os.path.join(os.path.dirname(__file__), 'b2b_crm.sqlite')
    # If db exists, remove it to start fresh
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 1. 客户表：解决名称歧义 (小米 vs 小米粒)、归属关系 (Owner/SalesTeam)
    c.execute('''CREATE TABLE IF NOT EXISTS customer (
        customer_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,       -- 全称
        short_name TEXT,          -- 简称
        is_main_customer BOOLEAN, -- 是否主客户
        customer_level TEXT,      -- 客户等级 (Strategic, KA, NA)
        owner TEXT,               -- 负责人
        sales_team TEXT,          -- 销售团队
        industry TEXT,
        status TEXT
    )''')

    # 2. 收入表：解决 "最近3个月收入"、"分产品收入"
    c.execute('''CREATE TABLE IF NOT EXISTS revenue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id TEXT,
        year_month TEXT,          -- 计收月份 (YYYY-MM)
        product_category TEXT,    -- 产品分类 (AI, Cloud)
        product_name TEXT,        -- 产品名称 (Model Inference, GPU)
        amount REAL,              -- 收入金额
        FOREIGN KEY(customer_id) REFERENCES customer(customer_id)
    )''')

    # 3. 用量表：解决 "最近3天调用量"、"Tokens趋势" (日粒度)
    c.execute('''CREATE TABLE IF NOT EXISTS resource_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id TEXT,
        usage_date TEXT,          -- 用量日期 (YYYY-MM-DD)
        resource_type TEXT,       -- 资源类型 (Tokens, GPU_Hours)
        model_or_card TEXT,       -- 模型/卡型 (DeepSeek, L20)
        quantity REAL,            -- 用量数值
        FOREIGN KEY(customer_id) REFERENCES customer(customer_id)
    )''')

    # 4. 信控表：解决 "信控额度"、"欠费"
    c.execute('''CREATE TABLE IF NOT EXISTS account_credit (
        customer_id TEXT PRIMARY KEY,
        total_credit_limit REAL,  -- 总信控额度
        available_balance REAL,   -- 可用余额
        arrears_amount REAL,      -- 欠费金额
        FOREIGN KEY(customer_id) REFERENCES customer(customer_id)
    )''')

    # --- 注入针对 Bad Case 的数据 ---
    
    # Case A: 模糊匹配 & 主客户逻辑 ("小米")
    customers = [
        ('ACC-001', '小米科技有限责任公司', '小米', 1, 'Strategic', 'ZhangSan', 'KA-North', 'Internet', 'Active'),
        ('ACC-002', '宁波小米粒鞋业有限公司', '小米粒', 0, 'SMB', 'LiSi', 'SME-East', 'Retail', 'Active'),
        ('ACC-003', '安宁市小米渣食品店', '小米渣', 0, 'SMB', 'WangWu', 'SME-South', 'Retail', 'Active'),
        ('ACC-004', '深圳市分期乐网络科技有限公司', '分期乐', 1, 'KA', 'ZhaoLiu', 'FinTech-Group', 'Finance', 'Active'),
        ('ACC-005', '网易（杭州）网络有限公司', '网易', 1, 'Strategic', 'SunBa', 'KA-East', 'Internet', 'Active'),
    ]
    c.executemany('INSERT OR REPLACE INTO customer VALUES (?,?,?,?,?,?,?,?,?)', customers)

    # Case B: 复杂时间窗口收入 ("小米最近3个月收入")
    # 假设当前是 2026-01，生成 2025-10 ~ 2025-12 的数据
    revenue_data = []
    for month in ['2025-10', '2025-11', '2025-12']:
        # 小米 (ACC-001) - 只有主客户有大额收入
        revenue_data.append(('ACC-001', month, 'AI', 'Model Inference', 12000000.00))
        # 小米粒 (ACC-002) - 极小金额
        revenue_data.append(('ACC-002', month, 'Cloud', 'VM', 5.50))
    
    # Case C: 分产品收入 ("网易 25年 Deepseek 收入")
    for m in range(1, 13):
        m_str = f"2025-{m:02d}"
        revenue_data.append(('ACC-005', m_str, 'AI', 'DeepSeek', 500000.00))

    c.executemany('INSERT INTO revenue (customer_id, year_month, product_category, product_name, amount) VALUES (?,?,?,?,?)', revenue_data)

    # Case D: 用量趋势 ("联想/小米 近3天调用量")
    usage_data = []
    # 使用当前日期作为基准，确保"最近3天"总是有数据
    today = datetime.now()
    base_date = today - timedelta(days=30)
    
    for i in range(31): # 生成过去30天到今天的数据
        d = (base_date + timedelta(days=i)).strftime('%Y-%m-%d')
        
        # 小米 (ACC-001) 每天调用量波动 (Doubao-Pro)
        # 正常波动: 100w + i*1w
        # 异常点注入: 15天前 (i=15) 突然飙升到 300w (是均值的约2-3倍)
        quantity = 1000000 + i*10000
        if i == 15:
            quantity = 3000000 # 异常点
            
        usage_data.append(('ACC-001', d, 'Tokens', 'Doubao-Pro', quantity))
        
        # 网易 (ACC-005) 使用 DeepSeek 模型
        usage_data.append(('ACC-005', d, 'Tokens', 'DeepSeek', 2000000 + i*50000))

    # Case E: 信控与欠费 ("分期乐信控余额" & "欠费仍在使用")
    # 分期乐 (ACC-004): 欠费 74w
    c.execute("INSERT OR REPLACE INTO account_credit VALUES ('ACC-004', 400000, -348787.45, 748787.45)")
    
    # 分期乐最近3天仍有 GPU 用量 (模拟风险场景)
    for i in range(3):
        d = (today - timedelta(days=i)).strftime('%Y-%m-%d')
        usage_data.append(('ACC-004', d, 'GPU_Hours', 'L20', 500))

    c.executemany('INSERT INTO resource_usage (customer_id, usage_date, resource_type, model_or_card, quantity) VALUES (?,?,?,?,?)', usage_data)

    conn.commit()
    conn.close()
    print(f"B2B 模拟数据库已生成: {db_path}")

if __name__ == "__main__":
    create_b2b_database()
