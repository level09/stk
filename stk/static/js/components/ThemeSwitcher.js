/**
 * ThemeSwitcher Component
 * Toggle between light and dark themes
 */

const ThemeSwitcher = {
  name: 'ThemeSwitcher',

  template: `
    <v-btn icon variant="text" size="small" @click="toggleTheme" :title="isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'">
      <i :class="isDark ? 'ti ti-sun' : 'ti ti-moon'" style="font-size: 22px;"></i>
    </v-btn>
  `,

  data() {
    return {
      isDark: false
    };
  },

  methods: {
    toggleTheme() {
      this.isDark = !this.isDark;

      // Update Vuetify theme
      if (this.$vuetify) {
        this.$vuetify.theme.global.name = this.isDark ? 'dark' : 'light';
      }

      // Save preference
      localStorage.setItem('stk-theme', this.isDark ? 'dark' : 'light');

      // Update window settings if available
      if (window.__settings__) {
        window.__settings__.dark = this.isDark;
      }
    },
  },

  mounted() {
    // config.js started the page in the saved theme.
    this.isDark = this.$vuetify.theme.global.name === 'dark';
  }
};
