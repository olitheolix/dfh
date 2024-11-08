export interface UAMUser {
    email: string; // uid
    name: string;
    lanid: string;
    slack: string;
    role: string;
    manager: string;
}

export interface UAMGroup {
    name: string; // uid
    owner: string;
    provider: string;
    description: string;
    users: string[];
    children: string[];
    roles: string[];
}

export interface UAMTreeNode {
    name: string; // uid
    children: { [key: string]: UAMTreeNode };
}

export interface UAMTreeInfo {
    groups: { [key: string]: UAMGroup };
    root: UAMTreeNode;
}

export interface UAMUserRoles {
    inherited: { [key: string]: string[] };
}

export const UAMGroupDefault: UAMGroup = {
    owner: "",
    name: "",
    description: "",
    provider: "",
    users: [],
    children: [],
    roles: [],
};

// Each row in the group data grid is just a group with a unique ID.
export interface DGGroupRow extends UAMGroup {
    id: string;
}

// Each row in the user data grid is just a user with a unique ID.
export interface DGUserRow extends UAMUser {
    id: string;
}

// Each row in the tree view is just a tree node with a unique ID.
export interface DGTreeNodeRow extends UAMTreeNode {
    id: string;
}

// Each row in the permission DataGrid denotes a role and a list of sources it
// was inherited from.
export interface DGUserRolesRow {
    id: string;
    role: string;
    sources: string[];
}

export interface DFHToken {
    email: string;
    token: string;
}

export interface UAMChild {
    child: string;
}
