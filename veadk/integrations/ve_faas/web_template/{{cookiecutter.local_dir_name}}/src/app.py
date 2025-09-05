# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from flask import Flask, render_template, request, redirect, url_for, flash, session
from models import db, Post, User
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.instance_path = os.path.join("/tmp", "flask_instance")
os.makedirs(app.instance_path, exist_ok=True)

db.init_app(app)

# 前台首页
@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.created_at.desc()).paginate(
        page=page, per_page=5, error_out=False)
    return render_template('index.html', posts=posts)

# 文章详情页
@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post.html', post=post)

# 后台登录页
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('用户名或密码错误')
    
    return render_template('admin/login.html')

# 后台登出
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

# 后台管理面板
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    post_count = Post.query.count()
    return render_template('admin/dashboard.html', post_count=post_count)

# 文章管理
@app.route('/admin/posts')
def admin_posts():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False)
    return render_template('admin/posts.html', posts=posts)

# 创建/编辑文章
@app.route('/admin/post', methods=['GET', 'POST'])
@app.route('/admin/post/<int:post_id>', methods=['GET', 'POST'])
def admin_edit_post(post_id=None):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    if post_id:
        post = Post.query.get_or_404(post_id)
    else:
        post = Post()
    
    if request.method == 'POST':
        post.title = request.form['title']
        post.content = request.form['content']
        
        if post_id is None:
            db.session.add(post)
        db.session.commit()
        flash('文章保存成功')
        return redirect(url_for('admin_posts'))
    
    return render_template('admin/edit_post.html', post=post)

# 删除文章
@app.route('/admin/post/delete/<int:post_id>', methods=['POST'])
def admin_delete_post(post_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash('文章删除成功')
    return redirect(url_for('admin_posts'))

if __name__ == '__main__':
    app.run(debug=True)