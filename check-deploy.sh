#!/bin/bash

echo "🔍 SEANews 部署配置检查"
echo "========================"
echo ""

# 1. 检查前端构建
echo "1️⃣ 检查前端构建..."
if [ -d "dist" ]; then
    echo "✅ dist 目录存在"
    if [ -f "dist/index.html" ]; then
        echo "✅ index.html 存在"
    else
        echo "❌ index.html 不存在，需要运行: npm run build"
    fi
    if [ -d "dist/assets" ]; then
        echo "✅ assets 目录存在"
        ASSET_COUNT=$(ls -1 dist/assets | wc -l)
        echo "   包含 $ASSET_COUNT 个文件"
    else
        echo "❌ assets 目录不存在"
    fi
else
    echo "❌ dist 目录不存在，需要运行: npm run build"
fi
echo ""

# 2. 检查环境变量文件
echo "2️⃣ 检查环境配置..."
if [ -f ".env" ]; then
    echo "✅ .env 文件存在"
    
    # 检查必需的环境变量
    REQUIRED_VARS=("OPENAI_API_KEY" "APP_USERNAME" "APP_PASSWORD" "APP_SECRET_KEY")
    for var in "${REQUIRED_VARS[@]}"; do
        if grep -q "^$var=" .env; then
            echo "✅ $var 已设置"
        else
            echo "❌ $var 未设置"
        fi
    done
else
    echo "❌ .env 文件不存在"
    echo "   请复制 .env.example 并填入配置"
fi
echo ""

# 3. 检查 Python 依赖
echo "3️⃣ 检查 Python 环境..."
if [ -f "server/requirements.txt" ]; then
    echo "✅ requirements.txt 存在"
    
    # 检查虚拟环境
    if [ -d ".venv" ]; then
        echo "✅ 虚拟环境存在"
    else
        echo "⚠️  虚拟环境不存在，建议创建: python -m venv .venv"
    fi
else
    echo "❌ requirements.txt 不存在"
fi
echo ""

# 4. 检查关键文件
echo "4️⃣ 检查关键配置文件..."
FILES=("Procfile" ".env.example" "package.json" "vite.config.js")
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file 存在"
    else
        echo "❌ $file 不存在"
    fi
done
echo ""

# 5. 检查 API 路由文件
echo "5️⃣ 检查后端配置..."
if [ -f "server/agno_api.py" ]; then
    echo "✅ agno_api.py 存在"
    
    # 检查关键导入
    if grep -q "from fastapi.staticfiles import StaticFiles" server/agno_api.py; then
        echo "✅ StaticFiles 已导入"
    else
        echo "❌ StaticFiles 未导入"
    fi
    
    if grep -q "FileResponse" server/agno_api.py; then
        echo "✅ FileResponse 已导入"
    else
        echo "❌ FileResponse 未导入"
    fi
else
    echo "❌ agno_api.py 不存在"
fi
echo ""

# 6. 检查 App.jsx 配置
echo "6️⃣ 检查前端 API 配置..."
if [ -f "src/App.jsx" ]; then
    echo "✅ App.jsx 存在"
    
    if grep -q "import.meta.env.DEV" src/App.jsx; then
        echo "✅ 环境检测逻辑已配置"
    else
        echo "⚠️  环境检测逻辑可能有问题"
    fi
else
    echo "❌ App.jsx 不存在"
fi
echo ""

# 总结
echo "========================"
echo "📋 检查完成！"
echo ""
echo "📝 下一步操作："
echo "1. 如果 dist 不存在: npm run build"
echo "2. 如果 .env 不存在: cp .env.example .env && 编辑填入真实值"
echo "3. 本地测试: npm run start:prod"
echo "4. 部署到 Zeabur: git push"
echo ""
