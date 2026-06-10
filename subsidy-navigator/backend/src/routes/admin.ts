import { Router, Request, Response, NextFunction } from 'express';
import { PrismaClient } from '@prisma/client';
import jwt from 'jsonwebtoken';
import bcrypt from 'bcryptjs';
import { z } from 'zod';
import { authMiddleware } from '../middleware/auth';
import { runFullScrape } from '../services/scraper';
import { createError } from '../middleware/errorHandler';

const router = Router();
const prisma = new PrismaClient();

const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

// POST /api/admin/login
router.post('/login', async (req: Request, res: Response, next: NextFunction) => {
  try {
    const parsed = loginSchema.safeParse(req.body);
    if (!parsed.success) {
      return next(createError('メールアドレスまたはパスワードが無効です', 400));
    }

    const { email, password } = parsed.data;
    const admin = await prisma.adminUser.findUnique({ where: { email } });

    if (!admin) {
      return next(createError('認証情報が正しくありません', 401));
    }

    const isValid = await bcrypt.compare(password, admin.passwordHash);
    if (!isValid) {
      return next(createError('認証情報が正しくありません', 401));
    }

    const secret = process.env.JWT_SECRET || 'default-secret';
    const token = jwt.sign(
      { id: admin.id, email: admin.email },
      secret,
      { expiresIn: '24h' }
    );

    res.json({
      data: { token, email: admin.email },
      error: null,
      meta: {},
    });
  } catch (err) {
    next(err);
  }
});

// GET /api/admin/stats (protected)
router.get('/stats', authMiddleware, async (_req: Request, res: Response, next: NextFunction) => {
  try {
    const [
      totalSubsidies,
      openSubsidies,
      totalMunicipalities,
      totalAlerts,
      totalConsultingRequests,
      recentSubsidies,
      categoryStats,
    ] = await Promise.all([
      prisma.subsidy.count(),
      prisma.subsidy.count({ where: { status: 'OPEN' } }),
      prisma.municipality.count(),
      prisma.alert.count({ where: { active: true } }),
      prisma.consultingRequest.count(),
      prisma.subsidy.findMany({
        take: 10,
        orderBy: { createdAt: 'desc' },
        include: { municipality: true },
      }),
      prisma.subsidy.groupBy({
        by: ['category'],
        _count: true,
        orderBy: { _count: { category: 'desc' } },
      }),
    ]);

    res.json({
      data: {
        totalSubsidies,
        openSubsidies,
        totalMunicipalities,
        totalAlerts,
        totalConsultingRequests,
        recentSubsidies,
        categoryStats: categoryStats.map(c => ({
          category: c.category,
          count: c._count,
        })),
      },
      error: null,
      meta: {
        generatedAt: new Date().toISOString(),
      },
    });
  } catch (err) {
    next(err);
  }
});

// POST /api/admin/scrape (protected)
router.post('/scrape', authMiddleware, async (_req: Request, res: Response, next: NextFunction) => {
  try {
    // Run scrape in background
    runFullScrape().catch(console.error);

    res.json({
      data: { message: 'スクレイピングを開始しました', startedAt: new Date().toISOString() },
      error: null,
      meta: {},
    });
  } catch (err) {
    next(err);
  }
});

// GET /api/admin/consulting (protected)
router.get('/consulting', authMiddleware, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { status, page = '1', limit = '20' } = req.query;
    const pageNum = parseInt(page as string, 10);
    const limitNum = Math.min(parseInt(limit as string, 10), 100);
    const skip = (pageNum - 1) * limitNum;

    const where: Record<string, unknown> = {};
    if (status) where.status = status as string;

    const [total, requests] = await Promise.all([
      prisma.consultingRequest.count({ where }),
      prisma.consultingRequest.findMany({
        where,
        orderBy: { createdAt: 'desc' },
        skip,
        take: limitNum,
      }),
    ]);

    res.json({
      data: requests,
      error: null,
      meta: { total, page: pageNum, limit: limitNum, totalPages: Math.ceil(total / limitNum) },
    });
  } catch (err) {
    next(err);
  }
});

// PATCH /api/admin/consulting/:id (protected)
router.patch('/consulting/:id', authMiddleware, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const { status } = req.body;
    const updated = await prisma.consultingRequest.update({
      where: { id: req.params.id },
      data: { status },
    });
    res.json({ data: updated, error: null, meta: {} });
  } catch (err) {
    next(err);
  }
});

// POST /api/admin/subsidies (protected)
router.post('/subsidies', authMiddleware, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const subsidy = await prisma.subsidy.create({
      data: req.body,
      include: { municipality: true },
    });
    res.status(201).json({ data: subsidy, error: null, meta: {} });
  } catch (err) {
    next(err);
  }
});

// PATCH /api/admin/subsidies/:id (protected)
router.patch('/subsidies/:id', authMiddleware, async (req: Request, res: Response, next: NextFunction) => {
  try {
    const updated = await prisma.subsidy.update({
      where: { id: req.params.id },
      data: req.body,
      include: { municipality: true },
    });
    res.json({ data: updated, error: null, meta: {} });
  } catch (err) {
    next(err);
  }
});

// DELETE /api/admin/subsidies/:id (protected)
router.delete('/subsidies/:id', authMiddleware, async (req: Request, res: Response, next: NextFunction) => {
  try {
    await prisma.subsidy.delete({ where: { id: req.params.id } });
    res.json({ data: { id: req.params.id, deleted: true }, error: null, meta: {} });
  } catch (err) {
    next(err);
  }
});

export default router;
