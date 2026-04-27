import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ArrowRight, Box, Code, Database, Lock, Settings, Store } from "lucide-react";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-secondary">
      {/* Header */}
      <header className="border-b border-border">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Store className="h-8 w-8 text-primary" />
            <h1 className="text-2xl font-bold">Minder Marketplace</h1>
          </div>
          <nav className="flex items-center gap-4">
            <Link href="/marketplace/plugins">
              <Button variant="ghost">Browse Plugins</Button>
            </Link>
            <Link href="/sign-in">
              <Button>Sign In</Button>
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <main className="container mx-auto px-4 py-16">
        <div className="text-center mb-16">
          <h2 className="text-5xl font-bold mb-4 bg-gradient-to-r from-primary to-purple-600 bg-clip-text text-transparent">
            Discover Amazing Plugins
          </h2>
          <p className="text-xl text-muted-foreground mb-8">
            Extend Minder with powerful plugins featuring AI tools, data connectors, and automation capabilities
          </p>
          <div className="flex gap-4 justify-center">
            <Link href="/marketplace/plugins">
              <Button size="lg" className="gap-2">
                Explore Plugins <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="/sign-in">
              <Button size="lg" variant="outline">
                Get Started
              </Button>
            </Link>
          </div>
        </div>

        {/* Features Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-16">
          <Card className="border-border bg-card/50 backdrop-blur">
            <CardHeader>
              <Box className="h-10 w-10 text-primary mb-2" />
              <CardTitle>AI Tools Integration</CardTitle>
              <CardDescription>
                Plugins come with their own AI tools and configurations
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Each plugin can define custom AI tools with OpenAI-compatible function calling,
                configuration schemas, and tier-based access control.
              </p>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardHeader>
              <Database className="h-10 w-10 text-primary mb-2" />
              <CardTitle>Seamless Integration</CardTitle>
              <CardDescription>
                One-click installation with automatic dependency management
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Browse, install, and configure plugins directly from the marketplace with
                smart dependency resolution and compatibility checking.
              </p>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardHeader>
              <Lock className="h-10 w-10 text-primary mb-2" />
              <CardTitle>Tier-Based Access</CardTitle>
              <CardDescription>
                Community, Professional, and Enterprise tiers with appropriate features
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Free and paid plugins with tier-based feature access control.
                Enable/disable plugins per installation as needed.
              </p>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardHeader>
              <Settings className="h-10 w-10 text-primary mb-2" />
              <CardTitle>Full Management</CardTitle>
              <CardDescription>
                Complete plugin lifecycle management with health monitoring
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Enable/disable plugins, monitor health status, track usage statistics,
                and manage configurations all from one dashboard.
              </p>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardHeader>
              <Code className="h-10 w-10 text-primary mb-2" />
              <CardTitle>Developer Friendly</CardTitle>
              <CardDescription>
                Submit plugins with visual manifest editor and testing tools
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Developers can submit plugins through an intuitive wizard, test AI tools,
                and generate documentation automatically.
              </p>
            </CardContent>
          </Card>

          <Card className="border-border bg-card/50 backdrop-blur">
            <CardHeader>
              <Store className="h-10 w-10 text-primary mb-2" />
              <CardTitle>Grafana-Style Experience</CardTitle>
              <CardDescription>
                Beautiful, intuitive interface inspired by Grafana marketplace
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Clean, modern interface with dark mode support, advanced search,
                filtering, and real-time updates.
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Stats Section */}
        <div className="grid md:grid-cols-3 gap-6 text-center">
          <div className="p-6">
            <div className="text-4xl font-bold text-primary mb-2">50+</div>
            <div className="text-sm text-muted-foreground">Available Plugins</div>
          </div>
          <div className="p-6">
            <div className="text-4xl font-bold text-primary mb-2">100+</div>
            <div className="text-sm text-muted-foreground">AI Tools</div>
          </div>
          <div className="p-6">
            <div className="text-4xl font-bold text-primary mb-2">3</div>
            <div className="text-sm text-muted-foreground">Access Tiers</div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border mt-16">
        <div className="container mx-auto px-4 py-8 text-center text-sm text-muted-foreground">
          <p>&copy; 2026 Minder. Powered by Next.js 14 and Clerk.</p>
        </div>
      </footer>
    </div>
  );
}