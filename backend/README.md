# OrderHub Backend API

Бекенд для CRM системи OrderHub - управління замовленнями для маркетплейсів.

## 🚀 Технології

- **Node.js** + **Express.js** - backend framework
- **TypeScript** - типізація
- **Prisma** - ORM для роботи з БД
- **SQLite** - база даних (для локальної розробки)
- **JWT** - автентифікація
- **bcrypt** - хешування паролів
- **Zod** - валідація даних

## 📦 Встановлення

### 1. Встановіть залежності

```bash
cd backend
npm install
```

### 2. Налаштуйте змінні середовища

Створіть файл `.env` на основі `.env.example`:

```bash
cp .env.example .env
```

Відредагуйте `.env`:

```env
DATABASE_URL="file:./dev.db"
JWT_SECRET="your-secret-key-change-this"
JWT_EXPIRES_IN="7d"
PORT=5000
FRONTEND_URL="http://localhost:3000"
```

### 3. Ініціалізуйте базу даних

```bash
# Генерація Prisma Client
npm run prisma:generate

# Створення міграцій та таблиць
npm run prisma:migrate

# Заповнення тестовими даними
npm run prisma:seed
```

### 4. Запустіть сервер

```bash
# Режим розробки з автоматичним перезапуском
npm run dev

# Або для продакшну
npm run build
npm start
```

Сервер запуститься на `http://localhost:5000`

## 📚 API Endpoints

### Authentication

- `POST /api/auth/register` - Реєстрація нового користувача
- `POST /api/auth/login` - Вхід в систему
- `GET /api/auth/profile` - Отримати профіль (потрібна автентифікація)

### Products

- `GET /api/products` - Список всіх продуктів
- `GET /api/products/:id` - Отримати продукт за ID
- `POST /api/products` - Створити новий продукт
- `PUT /api/products/:id` - Оновити продукт
- `DELETE /api/products/:id` - Видалити продукт

### Orders

- `GET /api/orders` - Список замовлень (з фільтрами)
- `GET /api/orders/:id` - Отримати замовлення за ID
- `POST /api/orders` - Створити нове замовлення
- `PATCH /api/orders/:id/status` - Оновити статус замовлення
- `PATCH /api/orders/:id/item-cost` - Оновити вартість товару
- `DELETE /api/orders/:id` - Видалити замовлення

### Integrations

- `GET /api/integrations` - Список інтеграцій
- `GET /api/integrations/:platform` - Отримати інтеграцію за платформою
- `POST /api/integrations` - Створити/оновити інтеграцію
- `POST /api/integrations/:platform/sync` - Синхронізувати з платформою
- `DELETE /api/integrations/:platform` - Видалити інтеграцію

## 🔐 Автентифікація

Всі захищені endpoints вимагають JWT токен у заголовку:

```
Authorization: Bearer YOUR_JWT_TOKEN
```

### Приклад реєстрації:

```bash
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "password123",
    "name": "User Name"
  }'
```

### Приклад входу:

```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@example.com",
    "password": "password"
  }'
```

Відповідь містить JWT токен:

```json
{
  "message": "Login successful",
  "user": {
    "id": "...",
    "email": "demo@example.com",
    "name": "Demo User"
  },
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

## 🗄️ База даних

### Prisma Studio

Для візуального перегляду та редагування бази даних:

```bash
npm run prisma:studio
```

Відкриється на `http://localhost:5555`

### Створення нових міграцій

```bash
npx prisma migrate dev --name your_migration_name
```

## 🔄 Перехід на PostgreSQL

Для продакшну замініть SQLite на PostgreSQL:

1. Встановіть PostgreSQL
2. Змініть в `prisma/schema.prisma`:

```prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}
```

3. Оновіть `.env`:

```env
DATABASE_URL="postgresql://user:password@localhost:5432/orderhub?schema=public"
```

4. Запустіть міграції:

```bash
npm run prisma:migrate
npm run prisma:seed
```

## 📝 Тестові дані

Після виконання seed команди створюються:

- **Користувач**: 
  - Email: `demo@example.com`
  - Password: `password`
  
- **5 продуктів**: футболки, чашки, постери, худі, кепки
- **3 тестових замовлення**: з різними статусами та джерелами

## 🛠️ Корисні команди

```bash
# Розробка
npm run dev                 # Запуск з nodemon
npm run build              # Компіляція TypeScript
npm start                  # Запуск продакшн версії

# Prisma
npm run prisma:generate    # Генерація Prisma Client
npm run prisma:migrate     # Застосування міграцій
npm run prisma:studio      # Відкрити Prisma Studio
npm run prisma:seed        # Заповнити БД тестовими даними
```

## 🚀 Deployment

### Для розгортання на сервері:

1. Встановіть PostgreSQL
2. Налаштуйте змінні середовища
3. Виконайте:

```bash
npm install
npm run prisma:generate
npm run prisma:migrate
npm run build
npm start
```

## 📌 TODO

- [ ] Реалізувати справжню інтеграцію з Shopify API
- [ ] Реалізувати справжню інтеграцію з Etsy API
- [ ] Додати rate limiting
- [ ] Додати логування (Winston/Morgan)
- [ ] Додати тести (Jest)
- [ ] Додати документацію API (Swagger)
- [ ] Додати email нотифікації
- [ ] Додати експорт звітів (CSV, PDF)

## 🤝 Підтримка

Для питань та підтримки звертайтеся до розробника.