from app import app, db
from models import User
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import OperationalError

def init_database():
    with app.app_context():
        try:
            # 创建所有数据库表
            db.metadata.create_all(bind=db.engine, checkfirst=True)
            print("数据库表创建成功")
        except OperationalError as e:
            if "table already exists" in str(e).lower():
                print("数据库表已存在，跳过创建")
            else:
                print(f"创建数据库表时出错: {e}")
                raise

        # 创建默认管理员账户（如不存在）
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                password=generate_password_hash('admin123')
            )
            db.session.add(admin)
            db.session.commit()
            print("默认管理员账户创建成功")
        else:
            print("默认管理员账户已存在，跳过创建")

if __name__ == '__main__':
    init_database()