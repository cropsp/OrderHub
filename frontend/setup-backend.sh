#!/bin/bash

# OrderHub Backend Setup Script
# Цей скрипт створює всю структуру папок та файлів для бекенду

echo "🚀 Starting OrderHub Backend Setup..."

# Перевірка чи ми в правильній папці
if [ ! -d "frontend" ]; then
    echo "❌ Error: frontend folder not found. Please run this script from OrderHub root directory"
    exit 1
fi

# Створення структури папок для backend
echo "📁 Creating backend folder structure..."

mkdir -p backend/src/controllers
mkdir -p backend/src/middleware
mkdir -p backend/src/routes
mkdir -p backend/src/types
mkdir -p backend/prisma

echo "✅ Folder structure created"

# Створення package.json
echo "📦 Creating package.json..."
cat > backend/package.json << 'EOF'
{
  "name": "orderhub-backend",
  "version": "1.0.0",
  "description": "Backend for OrderHub CRM",
  "main": "dist/server.js",
  "scripts": {
    "dev": "nodemon src/server.ts",
    "build": "tsc",
    "start": "node dist/server.js",
    "prisma:generate": "prisma generate",
    "prisma:migrate": "prisma migrate dev",
    "prisma:studio": "prisma studio",
    "prisma:seed": "ts-node prisma/seed.ts"
  },
  "keywords": ["crm", "orders", "management"],
  "author": "",
  "license": "ISC",
  "dependencies": {
    "@prisma/client": "^5.7.0",
    "bcryptjs": "^2.4.3",
    "cors": "^2.8.5",
    "dotenv": "^16.3.1",
    "express": "^4.18.2",
    "jsonwebtoken": "^9.0.2",
    "zod": "^3.22.4"
  },
  "devDependencies": {
    "@types/bcryptjs": "^2.4.6",
    "@types/cors": "^2.8.17",
    "@types/express": "^4.17.21",
    "@types/jsonwebtoken": "^9.0.5",
    "@types/node": "^20.10.5",
    "nodemon": "^3.0.2",
    "prisma": "^5.7.0",
    "ts-node": "^10.9.2",
    "typescript": "^5.3.3"
  }
}
EOF

# Створення tsconfig.json
echo "⚙️ Creating tsconfig.json..."
cat > backend/tsconfig.json << 'EOF'
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "lib": ["ES2022"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "moduleResolution": "node",
    "types": ["node"]
  },
  "include": ["src/**/*", "prisma/**/*"],
  "exclude": ["node_modules", "dist"]
}
EOF

# Створення nodemon.json
echo "⚙️ Creating nodemon.json..."
cat > backend/nodemon.json << 'EOF'
{
  "watch": ["src"],
  "ext": "ts,json",
  "ignore": ["src/**/*.spec.ts", "node_modules"],
  "exec": "ts-node src/server.ts"
}
EOF

# Створення .env.example
echo "🔒 Creating .env.example..."
cat > backend/.env.example << 'EOF'
# Database
DATABASE_URL="file:./dev.db"
# Для PostgreSQL використовуйте:
# DATABASE_URL="postgresql://user:password@localhost:5432/orderhub?schema=public"

# JWT
JWT_SECRET="your-super-secret-jwt-key-change-this-in-production"
JWT_EXPIRES_IN="7d"

# Server
PORT=5000
NODE_ENV="development"

# CORS
FRONTEND_URL="http://localhost:3000"

# Shopify Integration (optional)
SHOPIFY_API_KEY=""
SHOPIFY_API_SECRET=""

# Etsy Integration (optional)
ETSY_API_KEY=""
ETSY_API_SECRET=""
EOF

# Створення .gitignore для backend
echo "📝 Creating .gitignore..."
cat > backend/.gitignore << 'EOF'
# Dependencies
node_modules/

# Build
dist/

# Environment
.env

# Database
*.db
*.db-journal

# Logs
logs
*.log
npm-debug.log*

# OS
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.swp
*.swo
EOF

# Створення Prisma schema
echo "🗄️ Creating Prisma schema..."
cat > backend/prisma/schema.prisma << 'EOF'
// Prisma Schema для OrderHub CRM

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = env("DATABASE_URL")
}

model User {
  id        String   @id @default(uuid())
  email     String   @unique
  password  String
  name      String
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}

model Product {
  id        String      @id @default(uuid())
  sku       String      @unique
  name      String
  cost      Float
  price     Float
  createdAt DateTime    @default(now())
  updatedAt DateTime    @updatedAt
  orderItems OrderItem[]
}

model Order {
  id             String      @id @default(uuid())
  orderNumber    String      @unique
  date           DateTime    @default(now())
  source         String
  customerName   String
  customerEmail  String
  customerAddress String
  total          Float
  fees           Float       @default(0)
  status         String      @default("New")
  createdAt      DateTime    @default(now())
  updatedAt      DateTime    @updatedAt
  items          OrderItem[]
}

model OrderItem {
  id        String   @id @default(uuid())
  orderId   String
  productId String
  title     String
  quantity  Int
  price     Float
  cost      Float?
  order     Order    @relation(fields: [orderId], references: [id], onDelete: Cascade)
  product   Product  @relation(fields: [productId], references: [id])
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt

  @@index([orderId])
  @@index([productId])
}

model Integration {
  id        String   @id @default(uuid())
  platform  String   @unique
  apiKey    String
  apiSecret String
  isActive  Boolean  @default(true)
  lastSync  DateTime?
  createdAt DateTime @default(now())
  updatedAt DateTime @updatedAt
}
EOF

echo "✅ All configuration files created!"
echo ""
echo "📝 Next steps:"
echo "1. cd backend"
echo "2. npm install"
echo "3. cp .env.example .env"
echo "4. npm run prisma:generate"
echo "5. npm run prisma:migrate"
echo "6. npm run prisma:seed"
echo "7. npm run dev"
echo ""
echo "🎉 Backend setup complete! Now you need to copy the source files manually or I can create another script for that."
