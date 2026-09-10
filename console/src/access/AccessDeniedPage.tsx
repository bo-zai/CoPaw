import { LockOutlined } from "@ant-design/icons";

import styles from "./AccessDeniedPage.module.less";

export default function AccessDeniedPage() {
  return (
    <main className={styles.page}>
      <section className={styles.content} aria-labelledby="access-denied-title">
        <span className={styles.icon} aria-hidden="true">
          <LockOutlined />
        </span>
        <h1 id="access-denied-title">暂无访问权限</h1>
        <p>请通过已授权的业务系统进入，或联系管理员开通直接访问权限。</p>
      </section>
    </main>
  );
}
