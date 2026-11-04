/**
 * stk Components Registration
 * Registers all custom components globally on a Vue app
 */

function registerStkComponents(app) {
  // Register transition component
  app.component('transition-expand', TransitionExpand);

  // Register navigation components
  app.component('vertical-nav-link', VerticalNavLink);
  app.component('vertical-nav-group', VerticalNavGroup);
  app.component('vertical-nav-section-title', VerticalNavSectionTitle);

  // Register UI components
  app.component('notification-dropdown', NotificationDropdown);
  app.component('theme-switcher', ThemeSwitcher);

  // Vuetify 4 marks no theme on the page, so the root mirrors it as .dark-mode on <html> and <body>
  // for app CSS that switches with the theme, on every page and whatever changes the theme.
  app.mixin({
    mounted() {
      if (this !== this.$root) return;
      this.$watch(() => this.$vuetify.theme.global.name, name => {
        for (const el of [document.documentElement, document.body]) el.classList.toggle('dark-mode', name === 'dark');
      }, { immediate: true });
    },
  });

  // The app's own global components: define `function registerAppComponents(app)` in a script
  // loaded from _head.html, instead of copying this file.
  if (typeof registerAppComponents === 'function') registerAppComponents(app);

  return app;
}

/**
 * Helper to resolve which component to use for a nav item
 */
function resolveNavComponent(item) {
  if ('heading' in item) return 'vertical-nav-section-title';
  if ('children' in item) return 'vertical-nav-group';
  return 'vertical-nav-link';
}

/**
 * Filter navigation items by user role
 * @param {Array} items - Navigation items
 * @param {Array} userRoles - User's roles (e.g., ['admin', 'user'])
 * @returns {Array} Filtered navigation items
 */
function filterNavByRole(items, userRoles = []) {
  // Pure on purpose: this runs inside a computed, so mutating a nav item would
  // re-trigger that computed forever (Vue 3.5 prod loops instead of warning).
  return items
    .filter(item => !item.role || userRoles.includes(item.role))
    .map(item =>
      item.children
        ? { ...item, children: filterNavByRole(item.children, userRoles) }
        : item
    );
}
