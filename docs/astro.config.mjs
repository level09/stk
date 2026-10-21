// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
	site: 'https://docs.stk.dev',
	// old Mintlify URLs
	redirects: { '/introduction': '/', '/cursor-rules': '/ai-coding' },
	integrations: [
		starlight({
			title: 'stk',
			description: 'An async Quart framework for developers who ship. No build tools. No configuration maze.',
			logo: { light: './src/assets/logo-light.svg', dark: './src/assets/logo-dark.svg' },
			social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/level09/stk' }],
			editLink: { baseUrl: 'https://github.com/level09/stk/edit/master/docs/' },
			sidebar: [
				{ label: 'Getting Started', items: ['index', 'getting-started', 'build-loop'] },
				{ label: 'Core Features', items: ['authentication', 'deployment'] },
				{ label: 'Development', items: ['development', 'shell', 'ai-coding'] },
			],
		}),
	],
});
