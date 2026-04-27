#!/bin/bash

# Minder Plugin Marketplace - Setup Script

echo "🚀 Setting up Minder Plugin Marketplace..."

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+ first."
    exit 1
fi

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "❌ npm is not installed. Please install npm first."
    exit 1
fi

echo "✅ Node.js $(node -v) and npm $(npm -v) found"

# Install dependencies
echo "📦 Installing dependencies..."
npm install

# Check if .env.local exists, if not create from example
if [ ! -f .env.local ]; then
    echo "🔧 Creating .env.local from .env.example..."
    cp .env.example .env.local

    echo "⚠️  Please edit .env.local with your configuration:"
    echo "   - NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"
    echo "   - CLERK_SECRET_KEY"
    echo "   - NEXT_PUBLIC_API_URL"
    echo ""
    echo "   Get Clerk keys from: https://dashboard.clerk.com/"
else
    echo "✅ .env.local already exists"
fi

# Build the project
echo "🔨 Building the project..."
npm run build

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Setup completed successfully!"
    echo ""
    echo "🎯 Next steps:"
    echo "   1. Edit .env.local with your configuration"
    echo "   2. Start backend services: cd /root/minder && docker-compose up -d"
    echo "   3. Run development server: npm run dev"
    echo "   4. Open http://localhost:3000"
    echo ""
    echo "📚 For more information, see README.md"
else
    echo ""
    echo "❌ Build failed. Please check the errors above."
    exit 1
fi
