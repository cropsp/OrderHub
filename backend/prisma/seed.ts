import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcryptjs';

const prisma = new PrismaClient();

async function main() {
  console.log('🌱 Starting database seeding...');

  // Створення тестового користувача
  const hashedPassword = await bcrypt.hash('password', 10);
  
  const user = await prisma.user.upsert({
    where: { email: 'demo@example.com' },
    update: {},
    create: {
      email: 'demo@example.com',
      password: hashedPassword,
      name: 'Demo User'
    }
  });
  console.log('✅ Created user:', user.email);

  // Створення продуктів
  const products = await Promise.all([
    prisma.product.upsert({
      where: { sku: 'TS-BLK-L' },
      update: {},
      create: {
        sku: 'TS-BLK-L',
        name: 'Black T-Shirt (L)',
        cost: 5.50,
        price: 19.99
      }
    }),
    prisma.product.upsert({
      where: { sku: 'MUG-WHT-11' },
      update: {},
      create: {
        sku: 'MUG-WHT-11',
        name: 'White Coffee Mug (11oz)',
        cost: 3.25,
        price: 12.99
      }
    }),
    prisma.product.upsert({
      where: { sku: 'PST-ART-1824' },
      update: {},
      create: {
        sku: 'PST-ART-1824',
        name: 'Art Poster (18x24)',
        cost: 8.00,
        price: 25.00
      }
    }),
    prisma.product.upsert({
      where: { sku: 'HOOD-GRY-M' },
      update: {},
      create: {
        sku: 'HOOD-GRY-M',
        name: 'Gray Hoodie (M)',
        cost: 12.75,
        price: 39.99
      }
    }),
    prisma.product.upsert({
      where: { sku: 'CAP-NVY-OS' },
      update: {},
      create: {
        sku: 'CAP-NVY-OS',
        name: 'Navy Blue Cap',
        cost: 4.00,
        price: 15.99
      }
    })
  ]);
  console.log(`✅ Created ${products.length} products`);

  // Створення тестових замовлень
  const order1 = await prisma.order.create({
    data: {
      orderNumber: 'ORD-001',
      date: new Date('2023-10-26T10:00:00Z'),
      source: 'Shopify',
      customerName: 'John Doe',
      customerEmail: 'john.doe@example.com',
      customerAddress: '123 Main St, Anytown, USA',
      total: 45.97,
      fees: 2.30,
      status: 'New',
      items: {
        create: [
          {
            productId: products[0].id,
            title: 'Black T-Shirt (L)',
            quantity: 1,
            price: 19.99,
            cost: 5.50
          },
          {
            productId: products[1].id,
            title: 'White Coffee Mug (11oz)',
            quantity: 2,
            price: 12.99,
            cost: 3.25
          }
        ]
      }
    }
  });

  const order2 = await prisma.order.create({
    data: {
      orderNumber: 'ORD-002',
      date: new Date('2023-10-25T14:30:00Z'),
      source: 'Etsy',
      customerName: 'Jane Smith',
      customerEmail: 'jane.smith@example.com',
      customerAddress: '456 Oak Ave, Somewhere, USA',
      total: 25.00,
      fees: 1.75,
      status: 'In Progress',
      items: {
        create: [
          {
            productId: products[2].id,
            title: 'Art Poster (18x24)',
            quantity: 1,
            price: 25.00,
            cost: 8.00
          }
        ]
      }
    }
  });

  const order3 = await prisma.order.create({
    data: {
      orderNumber: 'ORD-003',
      date: new Date('2023-10-25T11:00:00Z'),
      source: 'Manual',
      customerName: 'Local Market',
      customerEmail: 'market@example.com',
      customerAddress: 'N/A',
      total: 199.95,
      fees: 0,
      status: 'Shipped',
      items: {
        create: [
          {
            productId: products[3].id,
            title: 'Gray Hoodie (M)',
            quantity: 5,
            price: 39.99,
            cost: 12.75
          }
        ]
      }
    }
  });

  console.log('✅ Created 3 test orders');

  console.log('🎉 Database seeding completed successfully!');
}

main()
  .catch((e) => {
    console.error('❌ Error during seeding:', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });