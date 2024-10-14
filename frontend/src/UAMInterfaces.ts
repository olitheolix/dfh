export interface UAMUser {
    uid: string;
    name: string;
}

export interface UAMGroup {
    uid: string;
    name: string;
    users: UAMUser[];
    children: UAMGroup[];
}
