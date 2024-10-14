export interface UAMUser {
    uid: string;
    name: string;
    lanid: string
    slack: string
    email: string
}

export interface UAMGroup {
    uid: string;
    name: string;
    owner: string
    type: string
    users: UAMUser[];
    children: UAMGroup[];
}

export interface POSTGroup {
    name: string;               // This is the text name; backend will assign UID
    ownerId: string;
}

export interface POSTGroupMembers {
    groupId: string;
    userIds: string[];
}
