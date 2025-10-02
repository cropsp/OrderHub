# OrderHub Backend Setup Script for Windows (PowerShell)
# Запускайте в Anaconda PowerShell Prompt

Write-Host "🚀 Starting OrderHub Backend Setup..." -ForegroundColor Green

# Перевірка чи існує папка frontend
if (-Not (Test-Path "frontend")) {
    Write-Host "❌ Error: frontend folder not found. Please run from OrderHub root directory" -ForegroundColor Red
    exit 1
}

# Створення структури папок
Write-Host "📁 Creating backend folder structure..." -ForegroundColor Cyan

$folders = @(
    "backend\src\controllers",
    "backend\src\middleware", 
    "backend\src\routes",
    "backend\src\types",
    "backend\prisma"
)

foreach ($folder in $folders) {
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
}

Write-Host "✅ Folder structure created" -ForegroundColor Green

# Створення package.json
Write-Host "📦 Creating package.json..." -ForegroundColor Cyan
@"
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
"@ | Out-File -FilePath "backend\package.json" -Encoding utf8

# Створення tsconfig.json
Write-Host "⚙️ Creating tsconfig.json..." -ForegroundColor Cyan
@"
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
"@ | Out-File -FilePath "backend\tsconfig.json" -Encoding utf8

# Створення nodemon.json
Write-Host "⚙️ Creating nodemon.json..." -ForegroundColor Cyan
@"
{
  "watch": ["src"],
  "ext": "ts,json",
  "ignore": ["src/**/*.spec.ts", "node_modules"],
  "exec": "ts-node src/server.ts"
}
"@ | Out-File -FilePath "backend\nodemon.json" -Encoding utf8

# Створення .env.example
Write-Host "🔒 Creating .env.example..." -ForegroundColor Cyan
@"
# Database
DATABASE_URL="file:./dev.db"

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
"@ | Out-File -FilePath "backend\.env.example" -Encoding utf8

# Створення .gitignore
Write-Host "📝 Creating .gitignore..." -ForegroundColor Cyan
@"
node_modules/
dist/
.env
*.db
*.db-journal
logs
*.log
npm-debug.log*
.DS_Store
Thumbs.db
.vscode/
.idea/
*.swp
*.swo
"@ | Out-File -FilePath "backend\.gitignore" -Encoding utf8

# Створення Prisma schema
Write-Host "🗄️ Creating Prisma schema..." -ForegroundColor Cyan
@"
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
"@ | Out-File -FilePath "backend\prisma\schema.prisma" -Encoding utf8

Write-Host ""
Write-Host "✅ Configuration files created!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Next steps:" -ForegroundColor Yellow
Write-Host "1. Copy source files from artifacts to backend/src/" -ForegroundColor White
Write-Host "2. cd backend" -ForegroundColor White
Write-Host "3. npm install" -ForegroundColor White
Write-Host "4. Copy-Item .env.example .env" -ForegroundColor White
Write-Host "5. npm run prisma:generate" -ForegroundColor White
Write-Host "6. npm run prisma:migrate" -ForegroundColor White
Write-Host "7. npm run prisma:seed" -ForegroundColor White
Write-Host "8. npm run dev" -ForegroundColor White
Write-Host ""
Write-Host "🎉 Setup complete!" -ForegroundColor Green
