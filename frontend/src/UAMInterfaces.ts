export interface UAMUser {
    email: string; // uid
    name: string;
    lanid: string;
    slack: string;
}

export interface UAMGroup {
    name: string; // uid
    owner: string;
    provider: string;
    users: { [key: string]: UAMUser };
    children: { [key: string]: UAMGroup };
}

// Each row in the group data grid is just a group with a unique ID.
export interface DGGroupRow extends UAMGroup {
    id: string;
}

// Each row in the user data grid is just a user with a unique ID.
export interface DGUserRow extends UAMUser {
    id: string;
}

export interface DFHToken {
    email: string;
    token: string;
}

export interface UAMChild {
    child: string;
}
