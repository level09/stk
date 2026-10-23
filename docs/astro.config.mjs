// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import starlightLlmsTxt from 'starlight-llms-txt';

export default defineConfig({
	site: 'https://docs.stk.dev',
	redirects: {
		// old Mintlify URLs
		'/introduction': '/',
		'/cursor-rules': '/ai-coding',
		// split into focused guides
		'/development': '/architecture',
	},
	integrations: [
		starlight({
			title: 'stk',
			plugins: [starlightLlmsTxt()],
			description: 'An async Quart framework for developers who ship. No build tools. No configuration maze.',
			logo: { light: './src/assets/logo-light.webp', dark: './src/assets/logo-dark.webp', alt: 'stk' },
			favicon: '/favicon.ico',
			social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/level09/stk' }],
			editLink: { baseUrl: 'https://github.com/level09/stk/edit/master/docs/' },
			sidebar: [
				{ label: 'Start', items: ['index', 'getting-started', 'build-loop', 'shell'] },
				{
					label: 'Guides',
					items: ['architecture', 'models', 'api', 'frontend', 'background-work', 'authentication'],
				},
				{ label: 'Agents', items: ['ai-coding'] },
				{ label: 'Deploy', items: ['deployment'] },
			],
		}),
	],
});
