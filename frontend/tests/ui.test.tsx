import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusTag } from "@/components/ui/StatusTag";
import { EmptyState } from "@/components/ui/EmptyState";

describe("StatusTag", () => {
  it("渲染后端状态对应的中文标签", () => {
    const { rerender } = render(<StatusTag status="succeeded" />);
    expect(screen.getByText("已完成")).toBeInTheDocument();

    rerender(<StatusTag status="over_budget" />);
    expect(screen.getByText("超预算")).toBeInTheDocument();

    rerender(<StatusTag status="weird_status" />);
    expect(screen.getByText("状态未知")).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("显示标题、说明和动作", () => {
    render(
      <EmptyState
        title="还没有项目"
        description="先建一个项目"
        action={<button type="button">创建</button>}
      />,
    );
    expect(screen.getByText("还没有项目")).toBeInTheDocument();
    expect(screen.getByText("先建一个项目")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "创建" })).toBeInTheDocument();
  });
});
