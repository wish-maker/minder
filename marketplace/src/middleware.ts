import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

// Protected routes that require authentication
const isProtectedRoute = createRouteMatcher([
  '/dashboard(.*)',
  '/admin(.*)',
  '/developer(.*)',
  '/api/(.*)',
]);

// Public routes that don't require authentication
const isPublicRoute = createRouteMatcher([
  '/',
  '/marketplace/(.*)',
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/api/auth/(.*)',
]);

// Admin routes that require admin role
const isAdminRoute = createRouteMatcher([
  '/admin(.*)',
]);

// TEMPORARILY DISABLED FOR TESTING - Clerk requires valid keys
export default function middleware(request: Request) {
  // Allow all routes for now
  return;
}

/* ORIGINAL CLERK MIDDLEWARE - RE-ENABLE AFTER GETTING VALID KEYS
export default clerkMiddleware((auth, request) => {
  // Allow public routes
  if (isPublicRoute(request)) {
    return;
  }

  // Protect routes that require authentication
  if (isProtectedRoute(request)) {
    auth().protect();

    // Additional admin role check for admin routes
    if (isAdminRoute(request)) {
      const session = auth();
      // You can add additional role checks here
      // For now, all authenticated users can access admin routes
      // In production, check: session?.publicMetadata?.role === 'admin'
    }
  }
});
*/

export const config = {
  matcher: [
    // Skip Next.js internals and static files
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
};