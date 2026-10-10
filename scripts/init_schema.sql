-- ============================================================
-- Makanan Production Relational Schema & Fintech Core
-- PostgreSQL 16 Initializer
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. ENUMS & DOMAINS
DO $$ BEGIN
  CREATE TYPE user_role AS ENUM ('student', 'partner', 'admin');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE meal_tier AS ENUM ('value', 'standard', 'premium');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE meal_category AS ENUM ('breakfast', 'lunch', 'dinner');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE meal_availability AS ENUM ('available', 'low_stock', 'unavailable');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE subscription_status AS ENUM ('active', 'expired', 'cancelled', 'pending');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE redemption_status AS ENUM ('pending', 'confirmed', 'cancelled', 'refunded');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE payment_status AS ENUM ('pending', 'completed', 'failed', 'refunded', 'expired');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE settlement_status AS ENUM ('pending', 'requested', 'processing', 'paid', 'cancelled');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 2. USERS & PROFILES
CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  full_name VARCHAR(255) NOT NULL DEFAULT '',
  student_id VARCHAR(100),
  role user_role NOT NULL DEFAULT 'student',
  avatar_url TEXT,
  phone VARCHAR(50),
  university VARCHAR(255) DEFAULT 'Albukhary International University',
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- 3. MEAL PLANS (Catalog)
CREATE TABLE IF NOT EXISTS meal_plans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  tier meal_tier NOT NULL,
  price_myr NUMERIC(10,2) NOT NULL CHECK (price_myr > 0),
  credits INTEGER NOT NULL CHECK (credits > 0),
  effective_rate NUMERIC(10,2) GENERATED ALWAYS AS (price_myr / credits) STORED,
  description TEXT,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. PARTNERS (Cafeterias / Vendors)
CREATE TABLE IF NOT EXISTS partners (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  name VARCHAR(255) NOT NULL,
  location VARCHAR(255),
  image_url TEXT,
  email VARCHAR(255),
  phone VARCHAR(50),
  description TEXT,
  status VARCHAR(50) DEFAULT 'active',
  rating NUMERIC(3,1) DEFAULT 4.5,
  meals_available INTEGER DEFAULT 0,
  meals_redeemed INTEGER DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_partners_user_id ON partners(user_id);

-- 5. PARTNER APPLICATIONS
CREATE TABLE IF NOT EXISTS partner_applications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_name VARCHAR(255) NOT NULL,
  owner_name VARCHAR(255) NOT NULL,
  email VARCHAR(255) NOT NULL,
  phone VARCHAR(50) NOT NULL,
  location VARCHAR(255) NOT NULL,
  address TEXT,
  opening_time VARCHAR(20),
  closing_time VARCHAR(20),
  operating_days TEXT[],
  description TEXT,
  cuisine_types TEXT[],
  seating_capacity INTEGER,
  status VARCHAR(50) NOT NULL DEFAULT 'pending',
  admin_notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 6. MEALS CATALOG
CREATE TABLE IF NOT EXISTS meals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  category meal_category NOT NULL,
  tier meal_tier NOT NULL,
  price_myr NUMERIC(10,2) NOT NULL DEFAULT 5.00,
  calories INTEGER,
  prep_time_minutes INTEGER,
  rating NUMERIC(3,1) DEFAULT 4.5,
  image_url TEXT,
  availability meal_availability NOT NULL DEFAULT 'available',
  is_active BOOLEAN NOT NULL DEFAULT true,
  redemption_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_meals_partner_id ON meals(partner_id);
CREATE INDEX IF NOT EXISTS idx_meals_category ON meals(category);
CREATE INDEX IF NOT EXISTS idx_meals_tier ON meals(tier);

-- 7. SETTLEMENTS (Must precede redemptions due to foreign key)
CREATE TABLE IF NOT EXISTS settlements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  partner_id UUID NOT NULL REFERENCES partners(id) ON DELETE CASCADE,
  period_start TIMESTAMPTZ NOT NULL,
  period_end TIMESTAMPTZ NOT NULL,
  total_redemptions INTEGER NOT NULL DEFAULT 0,
  total_amount_myr NUMERIC(10,2) NOT NULL DEFAULT 0.00,
  settlement_rate_myr NUMERIC(10,2) NOT NULL DEFAULT 0.00,
  status settlement_status NOT NULL DEFAULT 'pending',
  notes TEXT,
  payout_requested_at TIMESTAMPTZ,
  paid_at TIMESTAMPTZ,
  payment_reference VARCHAR(100),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_settlements_partner_id ON settlements(partner_id);
CREATE INDEX IF NOT EXISTS idx_settlements_status ON settlements(status);

-- 8. SUBSCRIPTIONS (Strict Concurrency & Integrity Constraints)
CREATE TABLE IF NOT EXISTS subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  meal_plan_id UUID NOT NULL REFERENCES meal_plans(id),
  status subscription_status NOT NULL DEFAULT 'active',
  credits_total INTEGER NOT NULL CHECK (credits_total >= 0),
  credits_used INTEGER NOT NULL DEFAULT 0 CHECK (credits_used >= 0),
  starts_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT chk_credits_used_max CHECK (credits_used <= credits_total)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_status ON subscriptions(user_id, status);

-- 9. REDEMPTIONS (Linked to Settlement)
CREATE TABLE IF NOT EXISTS redemptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subscription_id UUID NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
  meal_id UUID NOT NULL REFERENCES meals(id) ON DELETE RESTRICT,
  partner_id UUID REFERENCES partners(id) ON DELETE SET NULL,
  settlement_id UUID REFERENCES settlements(id) ON DELETE SET NULL,
  status redemption_status NOT NULL DEFAULT 'pending',
  qr_token TEXT NOT NULL,
  qr_code VARCHAR(100),
  redeemed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_redemptions_user_id ON redemptions(user_id);
CREATE INDEX IF NOT EXISTS idx_redemptions_partner_status ON redemptions(partner_id, status);
CREATE INDEX IF NOT EXISTS idx_redemptions_settlement_id ON redemptions(settlement_id);

-- 10. PAYMENTS (DuitNow QR & E-Wallets)
CREATE TABLE IF NOT EXISTS payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  meal_plan_id UUID NOT NULL REFERENCES meal_plans(id),
  subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
  amount_myr NUMERIC(10,2) NOT NULL CHECK (amount_myr > 0),
  payment_method VARCHAR(50) NOT NULL DEFAULT 'duitnow_qr',
  status payment_status NOT NULL DEFAULT 'pending',
  reference_code VARCHAR(100) NOT NULL UNIQUE,
  qr_data TEXT,
  gateway_transaction_id VARCHAR(255),
  expires_at TIMESTAMPTZ NOT NULL,
  paid_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_reference ON payments(reference_code);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);

-- 11. IMMUTABLE DOUBLE-ENTRY WALLET TRANSACTIONS
CREATE TABLE IF NOT EXISTS wallet_transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,
  redemption_id UUID REFERENCES redemptions(id) ON DELETE SET NULL,
  payment_id UUID REFERENCES payments(id) ON DELETE SET NULL,
  description VARCHAR(255) NOT NULL,
  credits_delta INTEGER NOT NULL,
  balance_after INTEGER NOT NULL CHECK (balance_after >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_wallet_user_id ON wallet_transactions(user_id, created_at DESC);

-- 12. NOTIFICATIONS & SUPPORT
CREATE TABLE IF NOT EXISTS notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  partner_id UUID REFERENCES partners(id) ON DELETE CASCADE,
  recipient_type VARCHAR(20) NOT NULL DEFAULT 'student',
  type VARCHAR(50) NOT NULL,
  title VARCHAR(255) NOT NULL,
  message TEXT NOT NULL,
  is_read BOOLEAN NOT NULL DEFAULT false,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_notif_partner ON notifications(partner_id, is_read);

CREATE TABLE IF NOT EXISTS support_tickets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  redemption_id UUID REFERENCES redemptions(id) ON DELETE SET NULL,
  category VARCHAR(50) NOT NULL DEFAULT 'other',
  subject VARCHAR(255) NOT NULL,
  description TEXT NOT NULL,
  status VARCHAR(50) NOT NULL DEFAULT 'open',
  admin_notes TEXT,
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  redemption_id UUID REFERENCES redemptions(id) ON DELETE SET NULL,
  meal_id UUID REFERENCES meals(id) ON DELETE SET NULL,
  partner_id UUID REFERENCES partners(id) ON DELETE SET NULL,
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  comment TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS waitlist_signup (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) NOT NULL UNIQUE,
  full_name VARCHAR(255) NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 13. SEED INITIAL PRODUCTION DATA
-- ============================================================

-- Seed Meal Plans
INSERT INTO meal_plans (id, name, tier, price_myr, credits, description) VALUES
  ('a1111111-1111-1111-1111-111111111111', 'Lite Saver', 'value', 150.00, 20, 'Perfect for light eaters — 20 meals per month at RM7.50/meal'),
  ('a2222222-2222-2222-2222-222222222222', 'Value Regular', 'value', 250.00, 60, 'Affordable daily meals — 60 meals per month at RM4.17/meal'),
  ('a3333333-3333-3333-3333-333333333333', 'Value Flex', 'value', 250.00, 40, 'Affordable meals with flexibility — 40 meals per month at RM6.25/meal'),
  ('a4444444-4444-4444-4444-444444444444', 'Standard Regular', 'standard', 300.00, 60, 'Balanced quality and frequency — 60 meals per month at RM5.00/meal'),
  ('a5555555-5555-5555-5555-555555555555', 'Standard Flex', 'standard', 300.00, 40, 'Better meals with flexibility — 40 meals per month at RM7.50/meal'),
  ('a6666666-6666-6666-6666-666666666666', 'Premium Regular', 'premium', 400.00, 60, 'Premium meals every day — 60 meals per month at RM6.67/meal'),
  ('a7777777-7777-7777-7777-777777777777', 'Premium Flex', 'premium', 400.00, 40, 'Top quality, fewer meals — 40 meals per month at RM10.00/meal')
ON CONFLICT (id) DO NOTHING;

-- Seed Admin User (admin@makanan.app / admin1234)
INSERT INTO users (id, email, password_hash, full_name, role)
VALUES (
  'b1111111-1111-1111-1111-111111111111',
  'admin@makanan.app',
  crypt('admin1234', gen_salt('bf', 10)),
  'Makanan Admin',
  'admin'
) ON CONFLICT (email) DO NOTHING;

-- Seed Demo Student (demo@makanan.app / demo1234)
INSERT INTO users (id, email, password_hash, full_name, student_id, role)
VALUES (
  'b2222222-2222-2222-2222-222222222222',
  'demo@makanan.app',
  crypt('demo1234', gen_salt('bf', 10)),
  'Ahmad Faiz',
  'AIU2024001',
  'student'
) ON CONFLICT (email) DO NOTHING;

-- Seed Demo Partner User (partner@makanan.app / partner1234)
INSERT INTO users (id, email, password_hash, full_name, role)
VALUES (
  'b3333333-3333-3333-3333-333333333333',
  'partner@makanan.app',
  crypt('partner1234', gen_salt('bf', 10)),
  'Cafeteria Manager',
  'partner'
) ON CONFLICT (email) DO NOTHING;

-- Seed Partners
INSERT INTO partners (id, user_id, name, location, image_url, email, status) VALUES
  ('c1111111-1111-1111-1111-111111111111', 'b3333333-3333-3333-3333-333333333333', 'School Cafeteria', 'AIU Main Building, Ground Floor', 'https://images.unsplash.com/photo-1567521464027-f127ff144326?w=400', 'cafeteria@aiu.edu.my', 'active'),
  ('c2222222-2222-2222-2222-222222222222', NULL, 'Mamak Stall', 'AIU Student Hub', 'https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=400', 'mamak@aiu.edu.my', 'active')
ON CONFLICT (id) DO NOTHING;

-- Seed Initial Meals
INSERT INTO meals (id, partner_id, name, description, category, tier, price_myr, calories, prep_time_minutes, rating, image_url, availability) VALUES
  ('d1111111-1111-1111-1111-111111111111', 'c1111111-1111-1111-1111-111111111111', 'Nasi Lemak', 'Fragrant coconut rice with sambal, anchovies, peanuts and boiled egg', 'breakfast', 'value', 4.50, 520, 10, 4.7, 'https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445?w=600', 'available'),
  ('d2222222-2222-2222-2222-222222222222', 'c1111111-1111-1111-1111-111111111111', 'Chicken Rice', 'Steamed chicken with fragrant rice and ginger sauce', 'lunch', 'standard', 5.50, 480, 15, 4.6, 'https://images.unsplash.com/photo-1604908176997-125f25cc6f3d?w=600', 'available'),
  ('d3333333-3333-3333-3333-333333333333', 'c1111111-1111-1111-1111-111111111111', 'Grilled Chicken Salad', 'Fresh greens with grilled chicken, egg and cherry tomatoes', 'lunch', 'premium', 7.50, 420, 15, 4.7, 'https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=600', 'available'),
  ('d4444444-4444-4444-4444-444444444444', 'c1111111-1111-1111-1111-111111111111', 'Mixed Curry Rice', 'Steamed rice with mixed vegetable curry and chicken', 'lunch', 'standard', 5.50, 550, 10, 4.5, 'https://images.unsplash.com/photo-1585937421612-70a008356fbe?w=600', 'available'),
  ('d5555555-5555-5555-5555-555555555555', 'c1111111-1111-1111-1111-111111111111', 'Fried Rice', 'Wok-fried rice with egg, vegetables and soy sauce', 'dinner', 'value', 4.50, 460, 12, 4.4, 'https://images.unsplash.com/photo-1603133872878-684f208fb84b?w=600', 'available'),
  ('d6666666-6666-6666-6666-666666666666', 'c1111111-1111-1111-1111-111111111111', 'Beef Rendang', 'Slow-cooked beef in rich coconut and spice gravy', 'dinner', 'premium', 8.00, 620, 20, 4.8, 'https://images.unsplash.com/photo-1574484284002-952d92456975?w=600', 'available'),
  ('d7777777-7777-7777-7777-777777777777', 'c2222222-2222-2222-2222-222222222222', 'Roti Canai', 'Flaky flatbread served with dhal and curry sauce', 'breakfast', 'value', 3.00, 380, 8, 4.6, 'https://images.unsplash.com/photo-1601050690597-df0568f70950?w=600', 'available'),
  ('d8888888-8888-8888-8888-888888888888', 'c2222222-2222-2222-2222-222222222222', 'Mee Goreng', 'Spicy stir-fried yellow noodles with egg and vegetables', 'lunch', 'value', 4.50, 490, 12, 4.5, 'https://images.unsplash.com/photo-1569050467447-ce54b3bbc37d?w=600', 'available'),
  ('d9999999-9999-9999-9999-999999999999', 'c2222222-2222-2222-2222-222222222222', 'Spicy Noodles', 'Wok-fried noodles with egg, chilli and bean sprouts', 'dinner', 'standard', 5.50, 510, 10, 4.8, 'https://images.unsplash.com/photo-1569718212165-3a8278d5f624?w=600', 'available')
ON CONFLICT (id) DO NOTHING;

-- Seed Demo Subscription for Demo Student (32 of 60 credits remaining)
INSERT INTO subscriptions (id, user_id, meal_plan_id, status, credits_total, credits_used, starts_at, expires_at)
VALUES (
  'e1111111-1111-1111-1111-111111111111',
  'b2222222-2222-2222-2222-222222222222',
  'a4444444-4444-4444-4444-444444444444',
  'active',
  60,
  28,
  CURRENT_TIMESTAMP - INTERVAL '15 days',
  CURRENT_TIMESTAMP + INTERVAL '15 days'
) ON CONFLICT (id) DO NOTHING;

INSERT INTO wallet_transactions (user_id, subscription_id, description, credits_delta, balance_after)
VALUES (
  'b2222222-2222-2222-2222-222222222222',
  'e1111111-1111-1111-1111-111111111111',
  'Meal plan purchased — 60 credits issued',
  60,
  60
) ON CONFLICT (id) DO NOTHING;
