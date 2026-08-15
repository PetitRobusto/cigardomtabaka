export type GuideFocusInstruction = {
  selector: string;
  action: 'focus';
  restoreId: string;
};

export type GuideRestoreInstruction = {
  restoreId: string;
  action: 'restore';
};

let nextRestoreId = 0;

/** 纯描述引导定位；DOM 层自行决定如何 query、聚焦和滚动。 */
export function resolveTarget(selector: string): GuideFocusInstruction {
  nextRestoreId += 1;
  return {
    selector,
    action: 'focus',
    restoreId: `guide-restore-${nextRestoreId}`,
  };
}

/** 纯描述离开引导时恢复原焦点，不触发任何业务动作。 */
export function restoreTarget(restoreId: string): GuideRestoreInstruction {
  return { restoreId, action: 'restore' };
}
