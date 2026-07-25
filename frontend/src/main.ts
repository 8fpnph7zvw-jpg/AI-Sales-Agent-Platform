import { createApp } from "vue";
import ElementPlus from "element-plus";
import zhCn from "element-plus/es/locale/lang/zh-cn";
import { createPinia } from "pinia";

import App from "./App.vue";
import { installPermissionDirective } from "./directives/permission";
import { router } from "./router";
import "./styles/index.scss";
import "element-plus/dist/index.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(ElementPlus, { locale: zhCn });
installPermissionDirective(app);
app.mount("#app");
