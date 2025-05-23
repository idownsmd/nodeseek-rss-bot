# 使用官方 Python 运行时作为父镜像
FROM python:3.9-slim

# 设置容器内的工作目录
WORKDIR /app

# 将依赖文件复制到工作目录
COPY requirements.txt ./

# 安装 requirements.txt 中指定的依赖包
RUN pip install --no-cache-dir -r requirements.txt

# 将当前目录的所有内容复制到容器的 /app 目录
COPY . .

# 创建数据持久化目录 (尽管脚本也会尝试创建，但在此声明更佳)
RUN mkdir -p /app/data

# 定义容器启动时执行的命令
CMD ["python", "bot.py"]