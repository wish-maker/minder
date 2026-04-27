# Minder Plugin Marketplace

A comprehensive Grafana-style plugin marketplace for the Minder platform with AI tools integration, tier-based access control, and plugin lifecycle management.

## 🎯 Features

### For Users
- **Plugin Discovery**: Browse and search plugins with advanced filtering
- **AI Tools Dashboard**: View and test all AI tools from installed plugins
- **AI Tools Detail Pages**: Individual tool testing with parameter input
- **Plugin Installation**: Multi-step installation wizard with configuration
- **User Dashboard**: Manage installed plugins, enable/disable functionality
- **Plugin Configuration**: Dynamic configuration modal for plugin settings
- **Tier-Based Access**: Community, Professional, and Enterprise tiers

### For Administrators
- **Admin Dashboard**: Platform overview with key metrics
- **Plugin Management**: Approve/reject plugins, manage featured status
- **Analytics Dashboard**: Installation trends, revenue metrics, user engagement
- **Content Moderation**: Review and moderate plugins and reviews
- **System Health**: Monitor service health and performance

### For Developers
- **Developer Portal**: Submit and manage your plugins
- **Plugin Submission Wizard**: Multi-step plugin submission workflow
- **AI Tools Integration**: Define AI tools in plugin manifests
- **Configuration Schema**: Dynamic configuration forms
- **Testing Tools**: Test plugins and AI tools before submission
- **Analytics**: Track plugin performance and revenue

## 🏗️ Architecture

### Frontend Stack
- **Framework**: Next.js 14 (App Router, Server Components)
- **UI Library**: shadcn/ui (modern, accessible components)
- **Styling**: Tailwind CSS (utility-first)
- **State Management**: React Query + Zustand
- **Authentication**: Clerk (JWT integration)

### Backend Integration
- **API Gateway**: Port 8000 (JWT auth, rate limiting)
- **Marketplace Service**: Port 8002 (Plugin CRUD, AI tools)
- **Plugin Registry**: Port 8001 (Plugin lifecycle, AI tools sync)

### Database Schema
- `marketplace_plugins`: Plugin metadata and configuration
- `marketplace_ai_tools_configurations`: AI tool schemas
- `marketplace_ai_tools_registrations`: Tool activations
- `marketplace_installations`: User installations

## 🚀 Getting Started

### Quick Start (One Command)

```bash
./start-dev.sh
```

This script will:
- ✅ Check and install dependencies
- ✅ Verify backend services are running
- ✅ Start the development server

Visit **http://localhost:3000** when ready.

### Manual Setup

#### Prerequisites
- Node.js 18+ and npm
- Docker and Docker Compose
- Backend services running (see [Backend Setup](#backend-setup))

#### Installation

1. **Install dependencies:**
   ```bash
   cd marketplace
   npm install
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env.local
   ```

   Edit `.env.local` with your configuration:
   ```env
   # API Configuration
   NEXT_PUBLIC_API_URL=http://localhost:8000

   # Clerk Authentication (get keys from https://dashboard.clerk.com/)
   NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_xxxxx
   CLERK_SECRET_KEY=sk_test_xxxxx

   # Application
   NEXT_PUBLIC_APP_URL=http://localhost:3000
   ```

3. **Run development server:**
   ```bash
   npm run dev
   ```

   Open [http://localhost:3000](http://localhost:3000) in your browser.

### Backend Setup

The marketplace requires backend services to be running:

1. **Start all services:**
   ```bash
   cd /root/minder
   docker-compose up -d
   ```

2. **Verify services:**
   - API Gateway: http://localhost:8000
   - Marketplace Service: http://localhost:8002
   - Plugin Registry: http://localhost:8001

## 📁 Project Structure

```
marketplace/
├── src/
│   ├── app/                      # Next.js app directory
│   │   ├── marketplace/         # User-facing pages
│   │   │   ├── plugins/         # Plugin catalog and details
│   │   │   ├── ai-tools/        # AI tools dashboard
│   │   │   │   └── [id]/        # AI tool detail and test page
│   │   │   └── [id]/            # Plugin detail page
│   │   │       └── install/     # Installation workflow
│   │   ├── dashboard/           # User dashboard
│   │   ├── admin/               # Admin pages
│   │   │   ├── plugins/         # Plugin management
│   │   │   └── analytics/       # Analytics dashboard
│   │   ├── developer/           # Developer portal
│   │   │   ├── plugins/         # Plugin management
│   │   │   └── plugins/new/     # Plugin submission wizard
│   │   ├── api/                 # API routes
│   │   ├── layout.tsx           # Root layout with Navbar
│   │   └── page.tsx             # Landing page
│   ├── components/
│   │   ├── ui/                  # shadcn/ui components
│   │   ├── marketplace/         # Marketplace components
│   │   ├── dashboard/           # Dashboard components
│   │   ├── modals/              # Modal components (config, etc.)
│   │   └── navigation/          # Navigation components
│   └── lib/
│       ├── api/                 # API client services
│       │   ├── client.ts        # HTTP client setup
│       │   ├── plugins.ts       # Plugin API calls
│       │   ├── ai-tools.ts      # AI tools API calls
│       │   └── plugins-management.ts  # Plugin management
│       └── types/               # TypeScript type definitions
└── public/                      # Static assets
```

## 🔌 API Integration

### Plugin Management
```typescript
// List plugins
const plugins = await pluginsApi.listPlugins({
  search: "ai",
  tier: "professional",
  pricing: "paid"
});

// Get plugin details
const plugin = await pluginsApi.getPlugin(pluginId);

// Install plugin
await pluginsApi.installPlugin(pluginId, config);
```

### AI Tools
```typescript
// Get all AI tools
const tools = await aiToolsApi.getAllAITools(true, "analysis", "professional");

// Get plugin AI tools
const tools = await aiToolsApi.getPluginAITools(pluginId);

// Enable/disable tool
await aiToolsApi.enableTool(toolId);
await aiToolsApi.disableTool(toolId);
```

### Plugin Management
```typescript
// Enable/disable plugin
await pluginsManagementApi.enablePlugin(pluginId);
await pluginsManagementApi.disablePlugin(pluginId);

// Test AI tool
const result = await pluginsManagementApi.testTool(toolId, params);

// Get plugin health
const health = await pluginsManagementApi.getPluginHealth(pluginId);
```

## 🎨 Design System

### Color Palette (Dark Mode)
```css
--primary: #3B82F6;      /* Blue */
--secondary: #8B5CF6;    /* Purple */
--success: #10B981;      /* Green */
--warning: #F59E0B;      /* Orange */
--danger: #EF4444;       /* Red */
--background: #0F172A;   /* Dark slate */
--surface: #1E293B;      /* Lighter slate */
--border: #334155;       /* Border color */
```

### Tier Colors
- **Community**: Green (#10B981)
- **Professional**: Blue (#3B82F6)
- **Enterprise**: Purple (#8B5CF6)

## 🔐 Authentication

The marketplace uses Clerk for authentication:

- **Public Routes**: `/`, `/marketplace/*`, `/sign-in`, `/sign-up`
- **Protected Routes**: `/dashboard`, `/admin/*`, `/developer/*`
- **Role-Based Access**: User, Admin, Developer roles

## 📊 Key Features

### 1. AI Tools Integration ⭐
Each plugin can define its own AI tools in the manifest:

```yaml
# manifest.yml
ai_tools:
  - name: text_analyzer
    type: analysis
    description: Analyze text for insights
    endpoint: /analyze
    method: POST
    parameters:
      text:
        type: string
        required: true
    required_tier: professional
```

### 2. AI Tools Testing Interface
- Individual tool detail pages
- Parameter input forms
- Real-time testing capability
- Result visualization
- Code examples for integration

### 3. Plugin Installation Workflow
Multi-step wizard with:
- Overview: Plugin information and requirements
- Configure: Dynamic form based on schema
- Confirm: Review configuration
- Installing: Progress indication
- Complete: Success confirmation

### 4. Plugin Management
- **Enable/Disable**: Toggle plugin status
- **Configure**: Update plugin configuration with modal interface
- **Health Check**: Monitor plugin health
- **Logs**: View plugin logs
- **Uninstall**: Remove plugin from system

### 5. Admin Features
- **Plugin Approval**: Review and approve/reject plugins
- **Featured Management**: Highlight popular plugins
- **Analytics**: View platform metrics and trends
- **Moderation**: Manage user-generated content

### 6. Developer Portal
- **Plugin Submission**: Multi-step submission wizard
- **Manifest Editor**: Define AI tools and configuration
- **Analytics**: Track plugin performance
- **Management**: Update plugin information

## 🧪 Testing

```bash
# Run tests
npm test

# Run linting
npm run lint

# Build for production
npm run build
```

## 🚢 Deployment

### Build
```bash
npm run build
```

### Start Production Server
```bash
npm start
```

### Docker Deployment
```bash
docker build -t minder-marketplace .
docker run -p 3000:3000 minder-marketplace
```

## 📚 Documentation

### Core Documentation
- **[COMPLETE_IMPLEMENTATION.md](./COMPLETE_IMPLEMENTATION.md)** - Full feature overview and architecture
- **[PLUGIN_AI_TOOLS_INTEGRATION.md](./PLUGIN_AI_TOOLS_INTEGRATION.md)** - Complete integration guide
- **[DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)** - Detailed deployment and testing instructions
- **[IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md)** - Technical summary and API services

### Backend Documentation
- [Backend API Documentation](../../services/marketplace/README.md)
- [Plugin Manifest Schema](../../services/marketplace/models/manifest_schema_v3.py)
- [Plugin Registry API](../../services/plugin-registry/README.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 License

This project is part of the Minder platform and uses the same license.

## 🎯 Implementation Status

### Phase 1: Foundation ✅ COMPLETE
- ✅ Next.js project setup
- ✅ shadcn/ui components
- ✅ Authentication with Clerk
- ✅ API client integration

### Phase 2: Core Marketplace ✅ COMPLETE
- ✅ Plugin catalog and detail pages
- ✅ AI tools dashboard
- ✅ Installation workflow
- ✅ User dashboard
- ✅ Plugin manifest viewer

### Phase 3: Admin & Management ✅ COMPLETE
- ✅ Admin dashboard
- ✅ Plugin management tools
- ✅ Analytics dashboard
- ✅ Content moderation
- ✅ Tier enforcement system

### Phase 4: Developer Experience ✅ COMPLETE
- ✅ Developer portal
- ✅ Plugin submission wizard
- ✅ Manifest editor
- ✅ Testing tools
- ✅ Documentation generator

**Overall Status: 🎉 100% COMPLETE - PRODUCTION READY**

## 💡 Support

For support and questions:
- GitHub Issues: [minder/issues](https://github.com/minder/minder/issues)
- Documentation: [minder/docs](https://docs.minder.io)
- Community: [minder discord](https://discord.gg/minder)
