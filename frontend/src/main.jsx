import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { WorkerSessionProvider } from "./session/WorkerSessionContext";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <WorkerSessionProvider>
        <App />
      </WorkerSessionProvider>
    </BrowserRouter>
  </React.StrictMode>
);
