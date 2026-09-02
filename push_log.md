01:02:23 [@astrojs/cloudflare] Enabling sessions with Cloudflare KV with the "SESSION" KV binding.
01:02:25 [content] Syncing content
01:02:25 [content] Synced content
01:02:25 [types] Generated 2.22s
01:02:25 [check] Getting diagnostics for Astro files in /Users/proto/Projects/@self/@wom/wom7web/apps/web...
src/content.config.ts:226:7 - warning ts(6133): 'contracts' is declared but its value is never read.

226 const contracts = defineCollection({
          ~~~~~~~~~
src/content.config.ts:187:7 - warning ts(6133): 'proposals' is declared but its value is never read.

187 const proposals = defineCollection({
          ~~~~~~~~~

src/components/BlueprintCard.astro:189:77 - warning ts(6385): 'event' is deprecated.

189     <div class="compare-section mt-2" onclick="((e) => e.stopPropagation())(event)">
                                                                                ~~~~~
src/components/BlueprintCard.astro:157:205 - warning ts(6385): 'event' is deprecated.

157               onclick="((e) => { e.preventDefault(); e.stopPropagation(); document.dispatchEvent(new CustomEvent('bp:quick-view', { detail: { id: e.currentTarget.closest('[data-bp-id]').dataset } })); })(event)"
                                                                                                                                                                                                                ~~~~~

src/components/DeploymentSlider.astro:252:13 - warning ts(6133): 'scale' is declared but its value is never read.

252       const scale = this.scales[step];
                ~~~~~

src/components/Footer.astro:6:1 - warning ts(6133): 'Image' is declared but its value is never read.

6 import { Image } from "astro:assets";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/Header.astro:29:1 - warning ts(6133): 'Image' is declared but its value is never read.

29 import { Image } from "astro:assets";
   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/Header.astro:2:1 - warning ts(6133): 'logger' is declared but its value is never read.

2 import { logger } from '@wom/logger';
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/Header.astro:92:3 - warning ts(6133): 'logger' is declared but its value is never read.

92   import { logger } from '@wom/logger';
     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/TechMiniIcon.astro:48:60 - warning ts(6133): 'onerror' is declared but its value is never read.

48         onerror="this.src='/icons/tech/fallback.svg'; this.onerror=null;"
                                                              ~~~~~~~
src/components/TechMiniIcon.astro:48:23 - warning ts(6133): 'src' is declared but its value is never read.

48         onerror="this.src='/icons/tech/fallback.svg'; this.onerror=null;"
                         ~~~

src/components/pages/BlueprintsPage.astro:9:1 - warning ts(6133): 'BlueprintCard' is declared but its value is never read.

9 import BlueprintCard from "../BlueprintCard.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/BlueprintsPage.astro:8:1 - warning ts(6133): 'StackVisualizer' is declared but its value is never read.

8 import StackVisualizer from "../StackVisualizer.svelte";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/BlueprintsPage.astro:7:1 - warning ts(6133): 'TechFilter' is declared but its value is never read.

7 import TechFilter from "../TechFilter.svelte";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/BlueprintsPage.astro:6:1 - warning ts(6133): 'Card' is declared but its value is never read.

6 import Card from "../ui/Card.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/BlueprintsPage.astro:5:1 - warning ts(6133): 'PageHero' is declared but its value is never read.

5 import PageHero from "../ui/PageHero.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/BlueprintsPage.astro:4:1 - warning ts(6133): 'Layout' is declared but its value is never read.

4 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/BlueprintsPage.astro:2:1 - warning ts(6133): 'logger' is declared but its value is never read.

2 import { logger } from '@wom/logger';
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/ContactPage.astro:4:1 - warning ts(6133): 'PageHero' is declared but its value is never read.

4 import PageHero from "../ui/PageHero.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ContactPage.astro:3:1 - warning ts(6133): 'Section' is declared but its value is never read.

3 import Section from "../ui/Section.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ContactPage.astro:2:1 - warning ts(6133): 'Layout' is declared but its value is never read.

2 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/HomePage.astro:11:1 - warning ts(6133): 'Section' is declared but its value is never read.

11 import Section from "../ui/Section.astro";
   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/HomePage.astro:10:1 - warning ts(6133): 'PageCTA' is declared but its value is never read.

10 import PageCTA from "../ui/PageCTA.astro";
   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/HomePage.astro:9:1 - warning ts(6133): 'PageHero' is declared but its value is never read.

9 import PageHero from "../ui/PageHero.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/HomePage.astro:7:1 - warning ts(6133): 'Button' is declared but its value is never read.

7 import Button from "@webomage/ui/lib/components/ui/Button.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/HomePage.astro:6:1 - warning ts(6133): 'NewsFeed' is declared but its value is never read.

6 import NewsFeed from "../../components/NewsFeed.svelte";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/HomePage.astro:4:1 - warning ts(6133): 'Layout' is declared but its value is never read.

4 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/NewsPage.astro:7:1 - warning ts(6133): 'NewsFeed' is declared but its value is never read.

7 import NewsFeed from "../NewsFeed.svelte";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/NewsPage.astro:6:1 - warning ts(6133): 'PageHero' is declared but its value is never read.

6 import PageHero from "../ui/PageHero.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/NewsPage.astro:5:1 - warning ts(6133): 'Section' is declared but its value is never read.

5 import Section from "../ui/Section.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/NewsPage.astro:4:1 - warning ts(6133): 'Layout' is declared but its value is never read.

4 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/ProcessPage.astro:2:1 - warning ts(6133): 'Layout' is declared but its value is never read.

2 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/ProjectsPage.astro:6:1 - warning ts(6133): 'PageHero' is declared but its value is never read.

6 import PageHero from "../ui/PageHero.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ProjectsPage.astro:5:1 - warning ts(6133): 'Button' is declared but its value is never read.

5 import Button from "@webomage/ui/lib/components/ui/Button.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ProjectsPage.astro:4:1 - warning ts(6133): 'Card' is declared but its value is never read.

4 import Card from "../ui/Card.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ProjectsPage.astro:3:1 - warning ts(6133): 'Section' is declared but its value is never read.

3 import Section from "../ui/Section.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ProjectsPage.astro:2:1 - warning ts(6133): 'Layout' is declared but its value is never read.

2 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/ServicesPage.astro:2:1 - warning ts(6133): 'Layout' is declared but its value is never read.

2 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/SolutionsPage.astro:2:1 - warning ts(6133): 'Layout' is declared but its value is never read.

2 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/templates/sections/ContactFormSection.astro:2:1 - warning ts(6133): 'logger' is declared but its value is never read.

2 import { logger } from '@wom/logger';
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/templates/sections/TeamSection.astro:40:58 - warning ts(6133): 'lang' is declared but its value is never read.

40 const { team_members, team_footer_text, team_footer_btn, lang = "en" } = Astro.props;
                                                            ~~~~
src/components/templates/sections/TeamSection.astro:40:41 - warning ts(6133): 'team_footer_btn' is declared but its value is never read.

40 const { team_members, team_footer_text, team_footer_btn, lang = "en" } = Astro.props;
                                           ~~~~~~~~~~~~~~~
src/components/templates/sections/TeamSection.astro:40:23 - warning ts(6133): 'team_footer_text' is declared but its value is never read.

40 const { team_members, team_footer_text, team_footer_btn, lang = "en" } = Astro.props;
                         ~~~~~~~~~~~~~~~~
src/components/templates/sections/TeamSection.astro:2:1 - warning ts(6133): 'logger' is declared but its value is never read.

2 import { logger } from '@wom/logger';
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/three/ArkanoidScene.ts:91:15 - warning ts(6133): 'pink' is declared but its value is never read.

91         const pink = 0xff00ff;
                 ~~~~
src/components/three/ArkanoidScene.ts:33:15 - warning ts(6133): 'purple' is declared but its value is never read.

33         const purple = 0x9900ff;
                 ~~~~~~
src/components/three/ArkanoidScene.ts:32:15 - warning ts(6133): 'red' is declared but its value is never read.

32         const red = 0xff3300;
                 ~~~
src/components/three/ArkanoidScene.ts:31:15 - warning ts(6133): 'yellow' is declared but its value is never read.

31         const yellow = 0xffff00;
                 ~~~~~~
src/components/three/ArkanoidScene.ts:30:15 - warning ts(6133): 'cyan' is declared but its value is never read.

30         const cyan = 0x00ffff;
                 ~~~~

src/components/three/DriftScene.ts:52:15 - warning ts(6133): 'factor' is declared but its value is never read.

52         const factor = delta * 60;
                 ~~~~~~

src/components/three/GameScene.ts:79:27 - warning ts(6133): 'settings' is declared but its value is never read.

79     public updateSettings(settings: Record<string, any>): void {
                             ~~~~~~~~

src/components/three/JunieScene.ts:14:13 - warning ts(6133): 'lastClick' is declared but its value is never read.

14     private lastClick = { x: 0, y: 0, time: 0 };
               ~~~~~~~~~

src/components/three/PacmanScene.ts:25:13 - warning ts(6133): 'moveProgress' is declared but its value is never read.

25     private moveProgress = 0;
               ~~~~~~~~~~~~

src/components/three/SolitaireScene.ts:123:15 - warning ts(6133): 'leftWall' is declared but its value is never read.

123         const leftWall = -35;
                  ~~~~~~~~
src/components/three/SolitaireScene.ts:122:15 - warning ts(6133): 'rightWall' is declared but its value is never read.

122         const rightWall = 35; // Or whatever visually
                  ~~~~~~~~~

src/components/three/SpectrumScene.ts:33:34 - warning ts(6133): 'i' is declared but its value is never read.

33         geometries.forEach((geo, i) => {
                                    ~

src/components/three/StarryNightScene.ts:107:13 - warning ts(6133): 'starColor' is declared but its value is never read.

107     private starColor = new THREE.Color(0xffffff);
                ~~~~~~~~~

src/components/three/TetrisScene.ts:183:13 - warning ts(6133): 'clearLines' is declared but its value is never read.

183     private clearLines() {
                ~~~~~~~~~~
src/components/three/TetrisScene.ts:103:31 - warning ts(6133): 'type' is declared but its value is never read.

103     private calculateBestMove(type: TetrominoType): { x: number, rotation: number } {
                                  ~~~~
src/components/three/TetrisScene.ts:42:13 - warning ts(6133): 'pieces' is declared but its value is never read.

42     private pieces: THREE.Group[] = [];
               ~~~~~~

src/components/three/WarpScene.ts:76:23 - warning ts(6133): 'positions' is declared but its value is never read.

76                 const positions = star.mesh.geometry.attributes.position.array as Float32Array;
                         ~~~~~~~~~

src/components/ui/Codemap.astro:176:15 - warning ts(6133): 'root' is declared but its value is never read.

176         const root = document.getElementById("codemap-root");
                  ~~~~

src/lib/otel-server.ts:130:31 - warning ts(6133): 'name' is declared but its value is never read.

130             startActiveSpan: (name: string, cb: any) => {
                                  ~~~~
src/lib/otel-server.ts:111:31 - warning ts(6133): 'name' is declared but its value is never read.

111             startActiveSpan: (name: string, cb: any) => cb({
                                  ~~~~

src/lib/vault.ts:65:12 - warning ts(6133): 'filepath' is declared but its value is never read.

65     const [filepath, module] = entry as [string, any];
              ~~~~~~~~

src/pages/_showcase.astro:15:7 - warning ts(6133): 'lang' is declared but its value is never read.

15 const lang = "en";
         ~~~~
src/pages/_showcase.astro:6:1 - warning ts(6133): 'Section' is declared but its value is never read.

6 import Section from "../components/ui/Section.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/pages/api/debug-auth-env.ts:5:39 - warning ts(6133): 'request' is declared but its value is never read.

5 export const GET: APIRoute = async ({ request, locals }) => {
                                        ~~~~~~~

src/pages/api/admin/images.ts:21:16 - warning ts(6133): 'ensureDir' is declared but its value is never read.

21 async function ensureDir(fs: any, dirPath: string) {
                  ~~~~~~~~~

src/pages/api/auth/me.ts:6:21 - warning ts(6133): 'request' is declared but its value is never read.

6     const { locals, request } = context;
                      ~~~~~~~

src/pages/api/sync/vault.ts:46:49 - warning ts(6133): 'locals' is declared but its value is never read.

46 export const POST: APIRoute = async ({ request, locals }) => {
                                                   ~~~~~~

src/pages/api/webhooks/linkedin.ts:73:49 - warning ts(6133): 'locals' is declared but its value is never read.

73 export const POST: APIRoute = async ({ request, locals }) => {
                                                   ~~~~~~
src/pages/api/webhooks/linkedin.ts:33:44 - warning ts(6133): 'locals' is declared but its value is never read.

33 export const GET: APIRoute = async ({ url, locals }) => {
                                              ~~~~~~

src/pages/blueprints/[...slug].astro:2:1 - warning ts(6133): 'logger' is declared but its value is never read.

2 import { logger } from '@wom/logger';
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Result (155 files): 
- 0 errors
- 0 warnings
- 74 hints

[astro] `markdown.remarkPlugins`, `markdown.rehypePlugins`, and `markdown.remarkRehype` are deprecated. Pass them to `unified({...})` from `@astrojs/markdown-remark` directly instead.
01:02:43 [@astrojs/cloudflare] Enabling compile-time image optimization. Images will be pre-optimized at build time.
01:02:43 [@astrojs/cloudflare] Enabling sessions with Cloudflare KV with the "SESSION" KV binding.
01:02:44 [content] Syncing content
01:02:44 [content] Synced content
01:02:44 [types] Generated 1.57s
01:02:44 [check] Getting diagnostics for Astro files in /Users/proto/Projects/@self/@wom/wom7web/apps/cp...
src/content.config.ts:293:7 - warning ts(6133): '_contracts' is declared but its value is never read.

293 const _contracts = defineCollection({
          ~~~~~~~~~~
src/content.config.ts:245:7 - warning ts(6133): '_proposals' is declared but its value is never read.

245 const _proposals = defineCollection({
          ~~~~~~~~~~

src/components/BlueprintCard.astro:189:48 - warning ts(6385): 'event' is deprecated.

189     <div class="compare-section mt-2" onclick="event.stopPropagation()">
                                                   ~~~~~
src/components/BlueprintCard.astro:157:48 - warning ts(6385): 'event' is deprecated.

157               onclick="event.preventDefault(); event.stopPropagation(); document.dispatchEvent(new CustomEvent('bp:quick-view', { detail: { id: this.closest('[data-bp-id]').dataset } }))"
                                                   ~~~~~
src/components/BlueprintCard.astro:157:24 - warning ts(6385): 'event' is deprecated.

157               onclick="event.preventDefault(); event.stopPropagation(); document.dispatchEvent(new CustomEvent('bp:quick-view', { detail: { id: this.closest('[data-bp-id]').dataset } }))"
                           ~~~~~

src/components/DeploymentSlider.astro:230:13 - warning ts(6133): 'scale' is declared but its value is never read.

230       const scale = this.scales[step];
                ~~~~~

src/components/Footer.astro:6:1 - warning ts(6133): 'Image' is declared but its value is never read.

6 import { Image } from "astro:assets";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/Header.astro:2:1 - warning ts(6133): 'logger' is declared but its value is never read.

2 import { logger } from '@wom/logger';
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/TechMiniIcon.astro:48:60 - warning ts(6133): 'onerror' is declared but its value is never read.

48         onerror="this.src='/icons/tech/fallback.svg'; this.onerror=null;"
                                                              ~~~~~~~
src/components/TechMiniIcon.astro:48:23 - warning ts(6133): 'src' is declared but its value is never read.

48         onerror="this.src='/icons/tech/fallback.svg'; this.onerror=null;"
                         ~~~

src/components/pages/BlueprintsPage.astro:9:1 - warning ts(6133): 'BlueprintCard' is declared but its value is never read.

9 import BlueprintCard from "../BlueprintCard.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/BlueprintsPage.astro:8:1 - warning ts(6133): 'StackVisualizer' is declared but its value is never read.

8 import StackVisualizer from "../StackVisualizer.svelte";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/BlueprintsPage.astro:7:1 - warning ts(6133): 'TechFilter' is declared but its value is never read.

7 import TechFilter from "../TechFilter.svelte";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/BlueprintsPage.astro:6:1 - warning ts(6133): 'Card' is declared but its value is never read.

6 import Card from "../ui/Card.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/BlueprintsPage.astro:5:1 - warning ts(6133): 'PageHero' is declared but its value is never read.

5 import PageHero from "../ui/PageHero.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/BlueprintsPage.astro:4:1 - warning ts(6133): 'Layout' is declared but its value is never read.

4 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/ContactPage.astro:4:1 - warning ts(6133): 'PageHero' is declared but its value is never read.

4 import PageHero from "../ui/PageHero.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ContactPage.astro:3:1 - warning ts(6133): 'Section' is declared but its value is never read.

3 import Section from "../ui/Section.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ContactPage.astro:2:1 - warning ts(6133): 'Layout' is declared but its value is never read.

2 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/HomePage.astro:11:1 - warning ts(6133): 'Section' is declared but its value is never read.

11 import Section from "../ui/Section.astro";
   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/HomePage.astro:10:1 - warning ts(6133): 'PageCTA' is declared but its value is never read.

10 import PageCTA from "../ui/PageCTA.astro";
   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/HomePage.astro:9:1 - warning ts(6133): 'PageHero' is declared but its value is never read.

9 import PageHero from "../ui/PageHero.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/HomePage.astro:7:1 - warning ts(6133): 'Button' is declared but its value is never read.

7 import Button from "@webomage/ui/lib/components/ui/Button.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/HomePage.astro:6:1 - warning ts(6133): 'NewsFeed' is declared but its value is never read.

6 import NewsFeed from "../../components/NewsFeed.svelte";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/HomePage.astro:4:1 - warning ts(6133): 'Layout' is declared but its value is never read.

4 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/NewsPage.astro:7:1 - warning ts(6133): 'NewsFeed' is declared but its value is never read.

7 import NewsFeed from "../NewsFeed.svelte";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/NewsPage.astro:6:1 - warning ts(6133): 'PageHero' is declared but its value is never read.

6 import PageHero from "../ui/PageHero.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/NewsPage.astro:5:1 - warning ts(6133): 'Section' is declared but its value is never read.

5 import Section from "../ui/Section.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/NewsPage.astro:4:1 - warning ts(6133): 'Layout' is declared but its value is never read.

4 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/ProcessPage.astro:2:1 - warning ts(6133): 'Layout' is declared but its value is never read.

2 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/ProjectsPage.astro:6:1 - warning ts(6133): 'PageHero' is declared but its value is never read.

6 import PageHero from "../ui/PageHero.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ProjectsPage.astro:5:1 - warning ts(6133): 'Button' is declared but its value is never read.

5 import Button from "@webomage/ui/lib/components/ui/Button.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ProjectsPage.astro:4:1 - warning ts(6133): 'Card' is declared but its value is never read.

4 import Card from "../ui/Card.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ProjectsPage.astro:3:1 - warning ts(6133): 'Section' is declared but its value is never read.

3 import Section from "../ui/Section.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/components/pages/ProjectsPage.astro:2:1 - warning ts(6133): 'Layout' is declared but its value is never read.

2 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/ServicesPage.astro:2:1 - warning ts(6133): 'Layout' is declared but its value is never read.

2 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/pages/SolutionsPage.astro:2:1 - warning ts(6133): 'Layout' is declared but its value is never read.

2 import Layout from "../../layouts/Layout.astro";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/templates/sections/ContactFormSection.astro:2:1 - warning ts(6133): 'logger' is declared but its value is never read.

2 import { logger } from '@wom/logger';
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/templates/sections/TeamSection.astro:40:58 - warning ts(6133): 'lang' is declared but its value is never read.

40 const { team_members, team_footer_text, team_footer_btn, lang = "en" } = Astro.props;
                                                            ~~~~
src/components/templates/sections/TeamSection.astro:40:41 - warning ts(6133): 'team_footer_btn' is declared but its value is never read.

40 const { team_members, team_footer_text, team_footer_btn, lang = "en" } = Astro.props;
                                           ~~~~~~~~~~~~~~~
src/components/templates/sections/TeamSection.astro:40:23 - warning ts(6133): 'team_footer_text' is declared but its value is never read.

40 const { team_members, team_footer_text, team_footer_btn, lang = "en" } = Astro.props;
                         ~~~~~~~~~~~~~~~~
src/components/templates/sections/TeamSection.astro:2:1 - warning ts(6133): 'logger' is declared but its value is never read.

2 import { logger } from '@wom/logger';
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/components/three/ArkanoidScene.ts:91:15 - warning ts(6133): 'pink' is declared but its value is never read.

91         const pink = 0xff00ff;
                 ~~~~
src/components/three/ArkanoidScene.ts:33:15 - warning ts(6133): 'purple' is declared but its value is never read.

33         const purple = 0x9900ff;
                 ~~~~~~
src/components/three/ArkanoidScene.ts:32:15 - warning ts(6133): 'red' is declared but its value is never read.

32         const red = 0xff3300;
                 ~~~
src/components/three/ArkanoidScene.ts:31:15 - warning ts(6133): 'yellow' is declared but its value is never read.

31         const yellow = 0xffff00;
                 ~~~~~~
src/components/three/ArkanoidScene.ts:30:15 - warning ts(6133): 'cyan' is declared but its value is never read.

30         const cyan = 0x00ffff;
                 ~~~~

src/components/three/DriftScene.ts:52:15 - warning ts(6133): 'factor' is declared but its value is never read.

52         const factor = delta * 60;
                 ~~~~~~

src/components/three/GameScene.ts:79:27 - warning ts(6133): 'settings' is declared but its value is never read.

79     public updateSettings(settings: Record<string, any>): void {
                             ~~~~~~~~

src/components/three/JunieScene.ts:14:13 - warning ts(6133): 'lastClick' is declared but its value is never read.

14     private lastClick = { x: 0, y: 0, time: 0 };
               ~~~~~~~~~

src/components/three/PacmanScene.ts:25:13 - warning ts(6133): 'moveProgress' is declared but its value is never read.

25     private moveProgress = 0;
               ~~~~~~~~~~~~

src/components/three/SolitaireScene.ts:123:15 - warning ts(6133): 'leftWall' is declared but its value is never read.

123         const leftWall = -35;
                  ~~~~~~~~
src/components/three/SolitaireScene.ts:122:15 - warning ts(6133): 'rightWall' is declared but its value is never read.

122         const rightWall = 35; // Or whatever visually
                  ~~~~~~~~~

src/components/three/SpectrumScene.ts:33:34 - warning ts(6133): 'i' is declared but its value is never read.

33         geometries.forEach((geo, i) => {
                                    ~

src/components/three/StarryNightScene.ts:107:13 - warning ts(6133): 'starColor' is declared but its value is never read.

107     private starColor = new THREE.Color(0xffffff);
                ~~~~~~~~~

src/components/three/TetrisScene.ts:183:13 - warning ts(6133): 'clearLines' is declared but its value is never read.

183     private clearLines() {
                ~~~~~~~~~~
src/components/three/TetrisScene.ts:103:31 - warning ts(6133): 'type' is declared but its value is never read.

103     private calculateBestMove(type: TetrominoType): { x: number, rotation: number } {
                                  ~~~~
src/components/three/TetrisScene.ts:42:13 - warning ts(6133): 'pieces' is declared but its value is never read.

42     private pieces: THREE.Group[] = [];
               ~~~~~~

src/components/three/WarpScene.ts:76:23 - warning ts(6133): 'positions' is declared but its value is never read.

76                 const positions = star.mesh.geometry.attributes.position.array as Float32Array;
                         ~~~~~~~~~

src/components/ui/Codemap.astro:176:15 - warning ts(6133): 'root' is declared but its value is never read.

176         const root = document.getElementById("codemap-root");
                  ~~~~

src/layouts/AdminLayout.astro:3:1 - warning ts(6133): 'Image' is declared but its value is never read.

3 import { Image } from "astro:assets";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/layouts/ClientLayout.astro:19:7 - warning ts(6133): 'role' is declared but its value is never read.

19 const role = Astro.locals.role;
         ~~~~
src/layouts/ClientLayout.astro:3:1 - warning ts(6133): 'Image' is declared but its value is never read.

3 import { Image } from "astro:assets";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/layouts/Layout.astro:24:7 - warning ts(6133): 'isDev' is declared but its value is never read.

24 const isDev = import.meta.env.DEV;
         ~~~~~

src/lib/otel-server.ts:130:31 - warning ts(6133): 'name' is declared but its value is never read.

130             startActiveSpan: (name: string, cb: any) => {
                                  ~~~~
src/lib/otel-server.ts:111:31 - warning ts(6133): 'name' is declared but its value is never read.

111             startActiveSpan: (name: string, cb: any) => cb({
                                  ~~~~

src/lib/vault.ts:65:12 - warning ts(6133): 'filepath' is declared but its value is never read.

65     const [filepath, module] = entry as [string, any];
              ~~~~~~~~

src/pages/sso.ts:30:13 - warning ts(6133): 'request' is declared but its value is never read.

30     const { request, url } = context;
               ~~~~~~~

src/pages/api/debug-auth-env.ts:5:39 - warning ts(6133): 'request' is declared but its value is never read.

5 export const GET: APIRoute = async ({ request, locals }) => {
                                        ~~~~~~~

src/pages/api/admin/images.ts:21:16 - warning ts(6133): 'ensureDir' is declared but its value is never read.

21 async function ensureDir(fs: any, dirPath: string) {
                  ~~~~~~~~~

src/pages/api/auth/linkedin-prefill.ts:16:48 - warning ts(6133): 'locals' is declared but its value is never read.

16 export const GET: APIRoute = async ({ cookies, locals }) => {
                                                  ~~~~~~

src/pages/api/sync/vault.ts:82:101 - warning ts(6387): The signature '(): $ZodFormattedError<{ contracts?: { id: string; title: string; data: Record<string, any>; client?: string | undefined; status?: string | undefined; }[] | undefined; proposals?: { id: string; data: Record<...>; }[] | undefined; jobs?: { ...; }[] | undefined; }, string>' of 'parseResult.error.format' is deprecated.

82         return new Response(JSON.stringify({ error: "Validation failed", details: parseResult.error.format() }), { status: 400 });
                                                                                                       ~~~~~~
src/pages/api/sync/vault.ts:46:49 - warning ts(6133): 'locals' is declared but its value is never read.

46 export const POST: APIRoute = async ({ request, locals }) => {
                                                   ~~~~~~

src/pages/api/webhooks/linkedin.ts:73:49 - warning ts(6133): 'locals' is declared but its value is never read.

73 export const POST: APIRoute = async ({ request, locals }) => {
                                                   ~~~~~~
src/pages/api/webhooks/linkedin.ts:33:44 - warning ts(6133): 'locals' is declared but its value is never read.

33 export const GET: APIRoute = async ({ url, locals }) => {
                                              ~~~~~~

src/pages/business/leads.astro:9:7 - warning ts(6133): 'refreshToken' is declared but its value is never read.

9 const refreshToken = Astro.cookies.get("sb-refresh-token")?.value;
        ~~~~~~~~~~~~

src/pages/business/treasury.astro:9:7 - warning ts(6133): 'refreshToken' is declared but its value is never read.

9 const refreshToken = Astro.cookies.get("sb-refresh-token")?.value;
        ~~~~~~~~~~~~

src/pages/business/blueprints/new.astro:6:1 - warning ts(6133): 'supabase' is declared but its value is never read.

6 import { supabase } from "../../../lib/supabase";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/pages/business/contracts/index.astro:14:28 - warning ts(6133): 'error' is declared but its value is never read.

14 const { data: dbContracts, error } = await supabase
                              ~~~~~

src/pages/business/proposals/index.astro:9:28 - warning ts(6133): 'error' is declared but its value is never read.

9 const { data: dbProposals, error } = await supabase
                             ~~~~~

src/pages/content/edit/[slug].astro:10:7 - warning ts(6133): 'supabaseUrl' is declared but its value is never read.

10 const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
         ~~~~~~~~~~~

src/pages/interviews/index.astro:9:7 - warning ts(6133): 'refreshToken' is declared but its value is never read.

9 const refreshToken = Astro.cookies.get("sb-refresh-token")?.value;
        ~~~~~~~~~~~~
src/pages/interviews/index.astro:8:7 - warning ts(6133): 'accessToken' is declared but its value is never read.

8 const accessToken = Astro.cookies.get("sb-access-token")?.value;
        ~~~~~~~~~~~
src/pages/interviews/index.astro:7:7 - warning ts(6133): 'supabaseKey' is declared but its value is never read.

7 const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
        ~~~~~~~~~~~
src/pages/interviews/index.astro:6:7 - warning ts(6133): 'supabaseUrl' is declared but its value is never read.

6 const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
        ~~~~~~~~~~~

src/pages/interviews/templates/index.astro:9:7 - warning ts(6133): 'refreshToken' is declared but its value is never read.

9 const refreshToken = Astro.cookies.get("sb-refresh-token")?.value;
        ~~~~~~~~~~~~
src/pages/interviews/templates/index.astro:8:7 - warning ts(6133): 'accessToken' is declared but its value is never read.

8 const accessToken = Astro.cookies.get("sb-access-token")?.value;
        ~~~~~~~~~~~
src/pages/interviews/templates/index.astro:7:7 - warning ts(6133): 'supabaseKey' is declared but its value is never read.

7 const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
        ~~~~~~~~~~~
src/pages/interviews/templates/index.astro:6:7 - warning ts(6133): 'supabaseUrl' is declared but its value is never read.

6 const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
        ~~~~~~~~~~~

src/pages/marketing/analytics.astro:11:7 - warning ts(6133): 'triggerSecret' is declared but its value is never read.

11 const triggerSecret = import.meta.env.WORKERS_WEBHOOK_SECRET;
         ~~~~~~~~~~~~~
src/pages/marketing/analytics.astro:10:7 - warning ts(6133): 'triggerUrl' is declared but its value is never read.

10 const triggerUrl = import.meta.env.WORKERS_WEBHOOK_URL;
         ~~~~~~~~~~

src/pages/marketing/connections.astro:5:1 - warning ts(6133): 'createClient' is declared but its value is never read.

5 import { createClient } from "@supabase/supabase-js";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

src/pages/system/debug.astro:6:7 - warning ts(6133): 'cookies' is declared but its value is never read.

6 const cookies = Astro.request.headers.get("cookie");
        ~~~~~~~

src/pages/system/users.astro:10:7 - warning ts(6133): 'refreshToken' is declared but its value is never read.

10 const refreshToken = Astro.cookies.get("sb-refresh-token")?.value;
         ~~~~~~~~~~~~
src/pages/system/users.astro:9:7 - warning ts(6133): 'accessToken' is declared but its value is never read.

9 const accessToken = Astro.cookies.get("sb-access-token")?.value;
        ~~~~~~~~~~~
src/pages/system/users.astro:8:7 - warning ts(6133): 'supabaseKey' is declared but its value is never read.

8 const supabaseKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
        ~~~~~~~~~~~
src/pages/system/users.astro:7:7 - warning ts(6133): 'supabaseUrl' is declared but its value is never read.

7 const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
        ~~~~~~~~~~~
src/pages/system/users.astro:5:1 - warning ts(6133): 'Collapsible' is declared but its value is never read.

5 import Collapsible from "../../components/admin/Collapsible.svelte";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
src/pages/system/users.astro:4:1 - warning ts(6133): 'RoleManager' is declared but its value is never read.

4 import RoleManager from "../../components/admin/RoleManager.svelte";
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

test-ssr.ts:3:41 - warning ts(6133): 'cookies' is declared but its value is never read.

3 export function getSupabaseServerClient(cookies: AstroCookies) {
                                          ~~~~~~~

Result (168 files): 
- 0 errors
- 0 warnings
- 100 hints

01:02:56 [@astrojs/cloudflare] Enabling image processing with Cloudflare Images for production with the "IMAGES" Images binding.
01:02:56 [@astrojs/cloudflare] Enabling sessions with Cloudflare KV with the "SESSION" KV binding.
01:02:58 [types] Generated 1.51s
01:02:58 [check] Getting diagnostics for Astro files in /Users/proto/Projects/@self/@wom/wom7web/apps/demo...
Result (5 files): 
- 0 errors
- 0 warnings
- 0 hints

⏳ [wom7web] Pre-push: w0m audit (scoped drift + openspec) — T96/T23...
w0m audit — HEAD 1cbc5288 — 2026-07-31 07:03 UTC

▶ DRIFT — git + specs
  ⚠️  WARN  [git] working tree — 2 uncommitted change(s)
  ⚠️  WARN  [git] branch beta — 5 ahead / 0 behind origin
  ✅ PASS  [spec] spec-drift gate — clean
  ✅ PASS  [spec] openspec validate --all --strict — all valid

▶ SECURITY — browser reputation (T120)
  ⚠️  WARN  [security] reputation-staleness — last confirmed 8d ago (>7d) — check Search Console → Security issues. Deceptive-pages flag active since ~2026-07-10; review REQUESTED 2026-07-22, verdict pending. Two open redirects found and fixed (shared handler in July, LinkedIn routes 2026-07-22). Full redirect sweep clean.
  ℹ️  INFO  [security] safe-browsing — set SAFE_BROWSING_API_KEY for an authoritative check instead of a staleness nudge

⚠️  audit: 0 fail · 3 warn · 2 pass
⏳ [wom7web] Pre-push: cross-repo dependency alignment (deps-policy)...
  ⚠  advisory @supabase/supabase-js: wom7ext @ ^2.87.1 (target ^2.110.7) — ^2.87.1 — 23 minors behind; bump needs an extension test, own change
  ✓ deps aligned across 4 repos (10 floors, 1 lockstep, pnpm 10.32.0); 1 advisory warning(s)
⏳ [wom7web] Pre-push: repo hygiene — required human-facing files (T135 AC5)...
✅ docs-check passed — repos=8, required_files=5, readme_sections=3, checked=40
✅ stacks registry conformant — 8 stacks, every declared command → a real `just` recipe
  → state-check (STATE.md freshness)...
  ℹ  ticket mirror up to date (150 tickets)
✅ state-check passed — STATE.md's mechanical block matches reality (enumerated 8 repo(s), 121 open ticket(s), 3 gate(s))
  → typecheck-ratchet (join/job may not gain type errors — T149/D6)...
▶ typecheck-ratchet — 2 app(s) below zero-gate: job, join (baseline measured 2026-07-27)
  ·  job: 107 errors, at baseline
  ·  join: 12 errors, at baseline

✅ typecheck-ratchet passed — no app gained type errors
  → hooks-check (declared gates wired · one sanctioned forge call)...
  ℹ  edge/typecheck exempt from the `just` contract — The hook runs from the REPO ROOT on staged files, where deno cannot di…
▶ hooks-check — 12 hook file(s) across 8 stack(s); 14 gated role(s) declared, 14 wired; forge allowlist = wom7web/.husky/pre-push
✅ hooks-check passed — every gated role is wired, and no unsanctioned forge call in any hook
  → version-check (one release format, one producer)...
✅ version-check passed — one declared format, one producer
  → tickets changed; mirroring to GitHub in background (log: .git/w0m-ticket-sync.log)
✅ [wom7web] Pre-push checks passed.
Enumerating objects: 66, done.
Counting objects: 100% (66/66), done.
Delta compression using up to 10 threads
Compressing objects: 100% (48/48), done.
Writing objects: 100% (50/50), 16.00 KiB | 4.00 MiB/s, done.
Total 50 (delta 41), reused 0 (delta 0), pack-reused 0 (from 0)
remote: Resolving deltas: 100% (41/41), completed with 15 local objects.
To github.com:casualuser/webomage.com.git
   f6e6fe1b..1cbc5288  beta -> beta

~/Projects/@self/@wom/wom7web beta* 1m 48s ❯ 
