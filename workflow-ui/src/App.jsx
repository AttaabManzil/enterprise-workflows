import { Routes, Route } from "react-router-dom";
import WorkflowList from "./WorkflowList";
import WorkflowDetails from "./WorkflowDetails";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<WorkflowList />} />
      <Route path="/workflows/:id" element={<WorkflowDetails />} />
    </Routes>
  );
}
