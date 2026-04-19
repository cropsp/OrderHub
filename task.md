# Project Tasks: OrderHub

## ✅ Completed Sprints
- [x] **Sprint 1 — Foundation** 🏗️
    - [x] Infrastructure & Config (.env, keys)
    - [x] Database initial migration & seed
    - [x] Frontend setup with Tailwind v4 & shadcn/ui
    - [x] Full stack verification (Docker up)

---

## 🚀 Sprint 2 — Core Backend API 📦 (Next)

- [ ] **Data Schemas** [Проста]
    - [ ] Create Pydantic schemas for all models (`backend/schemas/`)

- [ ] **Shops Management** [Проста]
    - [ ] Shop CRUD endpoints
    - [ ] Logic for encrypting/decrypting API tokens

- [ ] **Orders Logic** [Складна]
    - [ ] Order fetching with filters (status, shop_id, search)
    - [ ] `order_service.py` for status transitions and history
    - [ ] Pagination support

- [ ] **Etsy Integration** [Складна]
    - [ ] Etsy CSV parser service
    - [ ] Import endpoint (POST `/api/imports/etsy`)

- [ ] **Dashboard & Analytics** [Складна]
    - [ ] Service for revenue calculation per currency
    - [ ] Stat endpoints for the front page
